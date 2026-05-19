import random
import json
import os
import re
import time
from click import prompt
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from bot.models import BotTurnResponse, BotReactionResponse, BotOrderResponse
from diplomacy.engine.game import Game
from bot.random_bot import get_random_bot_orders
from deploy.backend.function_tools.db import add_agreement, get_trust_history
from function_tools.move_validator import check_internal_consistency
from function_tools.tactial_scorer import score_individual_orders

load_dotenv()

chat_histories = {}

def get_model(model_name="models/gemini-3.1-flash-lite-preview"):
    return ChatGoogleGenerativeAI(model=model_name, google_api_key=os.getenv("GEMINI_API_KEY"))

def invoke_with_retry(model, history, max_retries=4, initial_delay=5, bot_name="Bot"):
    for attempt in range(max_retries):
        try:
            return model.invoke(history)
        except Exception as e:
            err_msg = str(e).lower()
            if "429" in err_msg or "rate limit" in err_msg or "quota" in err_msg or "resource_exhausted" in err_msg:
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

def _get_common_context(game, bot_name, game_id, include_tactical=False):
    phase = game.get_current_phase()
    board_state = game.get_state()
    board_state_text = "\nCURRENT BOARD STATE:\n"
    for p in board_state.get('units', {}).keys():
        units = board_state['units'].get(p, [])
        centers = board_state['centers'].get(p, [])
        board_state_text += f"- {p}: {len(centers)} Supply Centers, {len(units)} Units\n"

    prev_turn_text = ""
    past_phases = game.get_phase_history()
    if past_phases:
        last_phase = past_phases[-1]
        prev_turn_text += f"\nPREVIOUS PHASE RESULTS:\n"
        last_results = getattr(last_phase, 'results', {})
        for loc, res in last_results.items():
            if res: prev_turn_text += f"- {loc}: {', '.join([str(r) for r in res])}\n"

    trust_history_text = ""
    if game_id:
        from function_tools.db import get_connection
        try:
            conn = get_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT agreed_with, agreement, followed, phase_made FROM trust_ledger WHERE game_id=%s AND bot_country=%s AND followed IS NOT NULL", (game_id, bot_name))
                for row in cur.fetchall():
                    trust_history_text += f"- {row[0]} {'FOLLOWED' if row[2] else 'BROKEN'} agreement from {row[3]}: '{row[1]}'\n"
            conn.close()
        except Exception: pass

    tactical_context = ""
    if include_tactical:
        scored_options = score_individual_orders(game, bot_name)
        tactical_context = "\nTACTICAL ANALYSIS (Top Orders per Unit):\n"
        for loc, options in scored_options.items():
            tactical_context += f"Unit {loc}:\n" + "".join([f"  - {opt['order']} (Score: {opt['score']})\n" for opt in options])

    return phase, board_state_text, prev_turn_text, trust_history_text, tactical_context

def _init_bot_history(bot_name, session_key):
    if session_key not in chat_histories:
        print(f"Creating new history for {session_key}")
        system_prompt = f"""We are playing Diplomacy. You are {bot_name}.
You are a pragmatic, highly competitive human player. You type quickly using lowercase, abbreviations, and sentence fragments (e.g., "rum", "bounce", "dmz"). Maintain a confident tone. Ensure your survival by forging alliances and staying paranoid.

STRICT RULES:
1. ORDER LIMIT: Provide ONE valid order for every unit location listed (when finalizing orders).
2. CONVOYS: Pair every Army 'VIA' with a corresponding Fleet 'C'.
3. SECRECY & MISDIRECTION: Guard your true tactical orders. Do not broadcast your literal moves in chat.
4. COMMUNICATION STYLE: Brevity (short fragments), lowercase text, ask questions rather than declaring your whole hand. Speak decisively without apologies. Only reply if necessary.
5. PLAUSIBLE LIES: Ground your communication, justifications, and misdirection in actual facts from the current board state (e.g., true unit positions, exact center counts). Pure fabrication is easily caught by humans who verify the board and talk to others.

MANAGING BETRAYALS (POST-STAB COMMUNICATION):
If you recently betrayed someone, broke an agreement, or are being accused of it, use one of these distinct strategies to manage fallout:
- Preemptive Gaslight: Claim you only attacked because you KNEW they were going to betray you first ("saw u plotting with england, had to protect myself"). Shift the blame.
- Mathematical Inevitability: Frame it as purely tactical business ("nothing personal, just needed the center to stop germany from winning").
- Crocodile Tears: Act like the decision agonized you or you were forced into it ("im so sorry man, france forced my hand otherwise he beats me").
- Ghosting: Simply do not reply to their angry messages (return an empty messages array to ignore them).
"""
        chat_histories[session_key] = [SystemMessage(content=system_prompt)]

def get_ai_bot_messages(game, bot_name: str, game_id: str):
    phase, board_state_text, prev_turn_text, trust_history_text, _ = _get_common_context(game, bot_name, game_id)
    session_key = f"{game_id}_{bot_name}"
    _init_bot_history(bot_name, session_key)
    
    prompt = f"""Current Phase: {phase}
{board_state_text}
{prev_turn_text}
{trust_history_text}

The communication phase has begun. Who do you want to talk to? Propose trades, probe for information, or distract. Do not announce your exact moves. Keep your message short and lowercase.
"""
    history = chat_histories[session_key]
    history.append(HumanMessage(content=prompt))
    
    try:
        response = invoke_with_retry(get_model().with_structured_output(BotTurnResponse), history, bot_name=bot_name)
        print(f"[{bot_name} Message Strategy]: {response.reasoning}")
        history.append(AIMessage(content=response.model_dump_json()))
        return [{"recipient": m.recipient, "message": m.message} for m in (response.messages or []) if m.recipient and m.message]
    except Exception as e:
        print(f"AI Bot Message Error for {bot_name}: {e}")
        return []

def finalize_ai_bot_orders(game, bot_name: str, game_id: str):
    valid_orders = {loc: game.get_all_possible_orders().get(loc, []) for loc in game.get_orderable_locations(bot_name)}
    if not valid_orders: return []

    phase, board_state_text, prev_turn_text, trust_history_text, tactical_context = _get_common_context(game, bot_name, game_id, include_tactical=True)
    session_key = f"{game_id}_{bot_name}"
    _init_bot_history(bot_name, session_key)

    prompt = f"""Current Phase: {phase}
The dialogue phase has ended. You must now finalize your real orders. Review the trust ledger, the tactical analysis, and the discussions you've had. Explain in your reasoning what you'll do, then submit your exact orders.

{trust_history_text}
{tactical_context}

Available Locations and Valid Options:
{json.dumps(valid_orders, indent=2)}
"""
    history = chat_histories[session_key]
    history.append(HumanMessage(content=prompt))
    model = get_model().with_structured_output(BotOrderResponse)
    
    for _ in range(3):
        try:
            data = invoke_with_retry(model, history, bot_name=bot_name)
            print(f"[{bot_name} Final Order Strategy]: {data.reasoning}")
            temp_orders = [o.order for o in data.orders if o.order]
            errs = check_internal_consistency(temp_orders)
            
            for item in data.orders:
                if item.location not in valid_orders: errs.append(f"Invalid location {item.location}")
                elif item.order not in valid_orders.get(item.location, []): errs.append(f"Invalid order '{item.order}' for {item.location}")
            
            if errs:
                history.append(AIMessage(content=data.model_dump_json()))
                history.append(HumanMessage(content=f"Fix these errors:\n{' '.join(errs)}"))
                continue
                
            history.append(AIMessage(content=data.model_dump_json()))
            return [o.order if o.order in valid_orders.get(o.location, []) else valid_orders[o.location][0] for o in data.orders]
        except Exception as e:
            continue
    return get_random_bot_orders(game, bot_name)[0]

def get_bot_messages(game, bot_name, bot_type="random", game_id=None):
    if bot_type == "ai" and game_id is not None:
        return get_ai_bot_messages(game, bot_name, game_id=game_id)
    return []

def get_bot_orders(game, bot_name, bot_type="random", game_id=None):
    if bot_type == "ai" and game_id is not None:
        return finalize_ai_bot_orders(game, bot_name, game_id=game_id)
    return get_random_bot_orders(game, bot_name)[0]
