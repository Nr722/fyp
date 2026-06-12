import random
import json
import os
import re
import time
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from bot.models import BotTurnResponse, BotOrderResponse
from bot.random_bot import get_random_bot_orders
from function_tools.move_validator import check_internal_consistency

load_dotenv()

chat_histories = {}

def get_model(model_name="models/gemini-3.1-flash-lite"):
    # No phantom args; LangChain detects SystemMessage natively now.
    return ChatGoogleGenerativeAI(model=model_name, google_api_key=os.getenv("GEMINI_API_KEY"))
    
def invoke_with_retry(model, history, max_retries=4, initial_delay=5, bot_name="Bot"):
    for attempt in range(max_retries):
        try:
            return model.invoke(history)
        except Exception as e:
            err_msg = str(e).lower()
            if "500" in err_msg or "internal server error" in err_msg:
                # Catching server-side crashes from Google AI Studio
                if attempt < max_retries - 1:
                    delay = initial_delay * (2 ** attempt)
                    print(f"DEBUG_SERVER_ERROR|{bot_name}|Retrying due to API 500 error in {delay}s...|Attempt {attempt + 1}")
                    time.sleep(delay)
                    continue
            elif "429" in err_msg or "rate limit" in err_msg or "quota" in err_msg or "resource_exhausted" in err_msg:
                if attempt < max_retries - 1:
                    delay = initial_delay * (2 ** attempt)
                    match = re.search(r'retry in ([0-9.]+)s', err_msg)
                    if match:
                        try:
                            delay = max(delay, float(match.group(1)) + 2.0)
                        except ValueError:
                            pass
                    print(f"DEBUG_TPM_LIMIT|{bot_name}|{delay:.1f}|{attempt + 1}")
                    time.sleep(delay)
                    continue
            raise e

def _get_board_context(game, bot_name):
    """Get minimal board state context without tactical analysis or trust history."""
    phase = game.get_current_phase()
    board_state = game.get_state()
    board_state_text = "\nCURRENT BOARD STATE:\n"
    for p in board_state.get('units', {}).keys():
        units = board_state['units'].get(p, [])
        centers = board_state['centers'].get(p, [])
        board_state_text += f"- {p}: {len(centers)} Supply Centers ({', '.join(centers)}), {len(units)} Units ({', '.join(units)})\n"

    prev_turn_text = ""
    past_phases = game.get_phase_history()
    if past_phases:
        last_phase = past_phases[-1]
        prev_turn_text = f"\nPREVIOUS PHASE ({last_phase.name}) ORDERS:\n"
        last_orders = getattr(last_phase, 'orders', {})
        has_orders = False
        for p, p_orders in last_orders.items():
            if p_orders:
                prev_turn_text += f"- {p}: {', '.join(p_orders)}\n"
                has_orders = True
        if not has_orders:
            prev_turn_text += "No active orders were submitted in the previous phase.\n"
            
        last_results = getattr(last_phase, 'results', {})
        prev_turn_text += "\nPREVIOUS PHASE RESULTS:\n"
        has_results = False
        for loc, res in last_results.items():
            if res:
                prev_turn_text += f"- {loc}: {', '.join([str(r) for r in res])}\n"
                has_results = True
        if not has_results:
            prev_turn_text += "No conflict/bouncing results in the previous phase.\n"

    return phase, board_state_text, prev_turn_text

def _init_bot_history(bot_name, session_key):
    """Initialize chat history with system prompt."""
    if session_key not in chat_histories:
        print(f"Creating new history for {session_key}")
        
        system_file = os.path.join(os.path.dirname(__file__), 'prompts', f'{bot_name.lower()}_system_prompt.txt')
        country_prompt = ""
        if os.path.exists(system_file):
            with open(system_file, 'r') as f:
                country_prompt = f.read()
                
        system_prompt = f"""We are playing Diplomacy. You are {bot_name}.
"""
        chat_histories[session_key] = [SystemMessage(content=system_prompt)]

def get_vanilla_bot_messages(game, bot_name: str, game_id: str):
    """Get bot messages without tactical analysis or database logging."""
    phase, board_state_text, prev_turn_text = _get_board_context(game, bot_name)
    session_key = f"{game_id}_{bot_name}"
    _init_bot_history(bot_name, session_key)
    
    prompt = f"""Current Phase: {phase}
{board_state_text}
{prev_turn_text}
Look at the previous turn's orders and results to see what the other players are trying to do, and use that to inform your strategy.
The communication phase has begun. 

Negotiate like a human player: use conditional offers, propose shared goals, or misdirect. Messages should be concise (1-2 sentences) and contain specific provinces, units, or targets. 
"""
    history = chat_histories[session_key]
    history.append(HumanMessage(content=prompt))
    
    try:
        model = get_model().with_structured_output(BotTurnResponse)
        response = invoke_with_retry(model, history, bot_name=bot_name)
        print(f"[{bot_name} Message Strategy]: {response.reasoning}")
        history.append(AIMessage(content=response.model_dump_json()))
        return [{"recipient": m.recipient, "message": m.message} for m in (response.messages or []) if m.recipient and m.message]
    except Exception as e:
        print(f"Vanilla Bot Message Error for {bot_name}: {e}")
        return []

def finalize_vanilla_bot_orders(game, bot_name: str, game_id: str):
    """Finalize bot orders without tactical analysis."""
    valid_orders = {loc: game.get_all_possible_orders().get(loc, []) for loc in game.get_orderable_locations(bot_name)}
    if not valid_orders: return []

    phase, board_state_text, prev_turn_text = _get_board_context(game, bot_name)
    session_key = f"{game_id}_{bot_name}"
    _init_bot_history(bot_name, session_key)

    prompt = f"""Current Phase: {phase}
{board_state_text}
{prev_turn_text}

The dialogue phase has ended. You must now finalize your real orders. Based on the board state and discussions, decide your strategy and submit your exact orders.
Available Locations and Valid Options:
{json.dumps(valid_orders, indent=2)}
"""
    history = chat_histories[session_key]
    history.append(HumanMessage(content=prompt))
    
    model = get_model().with_structured_output(BotOrderResponse)
    
    # -------------------------------------------------------------
    # MEMORY LEAK FIX: Isolate the retry block into a working copy
    # so runtime errors don't corrupt the long term session history
    # -------------------------------------------------------------
    working_history = list(history)
    
    for _ in range(3):
        try:
            data = invoke_with_retry(model, working_history, bot_name=bot_name)
            print(f"[{bot_name} Final Order Strategy]: {data.reasoning}")
            temp_orders = [o.order for o in data.orders if o.order]
            errs = check_internal_consistency(temp_orders)
            
            for item in data.orders:
                if item.location not in valid_orders: 
                    errs.append(f"Invalid location {item.location}")
                elif item.order not in valid_orders.get(item.location, []): 
                    errs.append(f"Invalid order '{item.order}' for {item.location}")
            
            if errs:
                # Append errors ONLY to the transient working history
                working_history.append(AIMessage(content=data.model_dump_json()))
                working_history.append(HumanMessage(content=f"Fix these errors:\n{' '.join(errs)}"))
                continue
                
            # If everything passes, sync back to the main history context once
            history.append(AIMessage(content=data.model_dump_json()))
            return [o.order if o.order in valid_orders.get(o.location, []) else valid_orders[o.location][0] for o in data.orders]
        except Exception as e:
            continue
            
    return get_random_bot_orders(game, bot_name)[0]

def get_vanilla_bot_orders(game, bot_name, game_id):
    """Get vanilla bot orders."""
    return finalize_vanilla_bot_orders(game, bot_name, game_id=game_id)