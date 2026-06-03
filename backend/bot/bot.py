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
from function_tools.db import add_agreement, get_trust_history
from function_tools.move_validator import check_internal_consistency
from function_tools.tactical_scorer import score_individual_orders

load_dotenv()

chat_histories = {}

def get_model(model_name="models/gemini-3.1-flash-lite"):
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

    trust_history_text = ""
    if game_id:
        from function_tools.db import get_connection
        try:
            conn = get_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT agreed_with, agreement, followed, phase_made FROM trust_ledger WHERE game_id=%s AND bot_country=%s", (game_id, bot_name))
                past_text = ""
                active_text = ""
                for row in cur.fetchall():
                    if row[2] is not None:
                        # Since score is out of 100, let's treat anything >= 50 as followed, else broken
                        status = "FOLLOWED" if int(row[2]) >= 50 else "BROKEN"
                        past_text += f"- {row[0]} {status} agreement from {row[3]}: '{row[1]}'\n"
                    else:
                        active_text += f"- Active agreement with {row[0]} (made in {row[3]}): '{row[1]}'\n"
                
                if past_text:
                    trust_history_text += "PAST TRUST HISTORY:\n" + past_text
                if active_text:
                    trust_history_text += "CURRENT ACTIVE AGREEMENTS (You MUST follow these early game unless stabbing is overwhelmingly advantageous):\n" + active_text
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
        
        system_file = os.path.join(os.path.dirname(__file__), 'prompts', f'{bot_name.lower()}_system_prompt.txt')
        country_prompt = ""
        if os.path.exists(system_file):
            with open(system_file, 'r') as f:
                country_prompt = f.read()
                
        system_prompt = f"""We are playing Diplomacy. You are {bot_name}.

<STRATEGY_AND_GOALS>
{country_prompt}
</STRATEGY_AND_GOALS>

CORE DIRECTIVES:
1. TONE & PERSONA: Act like a mature, friendly human Diplomacy player. Use concise, natural language (1-2 sentences per message).
2. TRANSACTIONAL DIPLOMACY: Always seek a quid pro quo. Propose strategic DMZs to secure flanks and offer conditional support ("I'll support X if you hold Y"). Only accept deals that actively advance your expansion or build trust without hurting your position or goals.
3. TRUST & GOSSIP: Trust is a weapon. Build broad partnerships by sharing specific (or plausibly fake) moves and bartering third-party intel. Reach out to non-adjacent players to build leverage. 
4. DECEPTION (THE STAB): Never threaten. Be friendly until the knife goes in. If invading, propose fake DMZs or ask for fake support to misdirect them. Only lie if it aligns logically with the board state—dumb lies destroy your utility.
5. Orders & Strategic Negotiation:
- You must converse with specifics. To win, you need active allies, which requires sharing concrete proposals and sometimes your moves if they dont leave you vulnerable.
- Practice Conditional Reciprocity: Do not blindly give away your final moves. Instead, offer "if-then" scenarios and mutual commitments. If a player shares a specific plan, match their level of specificity.
- Guard Against Exploitation: You are playing to win. If players' proposal leaves you completely vulnerable, politely push back for mutual guarantees before committing to details. You dont have to commit to anything if it puts you in a worse position.
5. CONFLICT MANAGEMENT: If betrayed, you can act vindictive. If you are caught backstabbing or need to defuse anger, use tactical apologies ("I was worried about Germany"), ask questions to deflect, or pivot their anger toward a larger shared enemy.
"""

        chat_histories[session_key] = [SystemMessage(content=system_prompt)]

def get_ai_bot_messages(game, bot_name: str, game_id: str, use_tactical: bool = True):
    phase, board_state_text, prev_turn_text, trust_history_text, tactical_context = _get_common_context(game, bot_name, game_id, include_tactical=use_tactical)
    session_key = f"{game_id}_{bot_name}"
    _init_bot_history(bot_name, session_key)
    
    prompt = f"""Current Phase: {phase}
{board_state_text}
{prev_turn_text}
{trust_history_text}
{tactical_context}
Look at the previous turn's orders and results to see what the other players are trying to do, and use that to inform your strategy.
The communication phase has begun. 

Negotiate like a human player: use conditional offers, propose shared goals, or misdirect. Messages should be concise (1-2 sentences) and contain specific provinces, units, or targets. 
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

def finalize_ai_bot_orders(game, bot_name: str, game_id: str, use_tactical: bool = True):
    valid_orders = {loc: game.get_all_possible_orders().get(loc, []) for loc in game.get_orderable_locations(bot_name)}
    if not valid_orders: return []

    phase, board_state_text, prev_turn_text, trust_history_text, tactical_context = _get_common_context(game, bot_name, game_id, include_tactical=use_tactical)
    session_key = f"{game_id}_{bot_name}"
    _init_bot_history(bot_name, session_key)

    prompt = f"""Current Phase: {phase}
    {trust_history_text}
    {tactical_context}

    The dialogue phase has ended. You must now finalize your real orders. Review the trust ledger, the tactical analysis, and the discussions you've had. Explain in your reasoning what you'll do, then submit your exact orders.
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

def get_bot_messages(game, bot_name, bot_type="random", game_id=None, use_tactical=True):
    if bot_type == "ai" and game_id is not None:
        return get_ai_bot_messages(game, bot_name, game_id=game_id, use_tactical=use_tactical)
    return []

def get_bot_orders(game, bot_name, bot_type="random", game_id=None, use_tactical=True):
    if bot_type == "ai" and game_id is not None:
        return finalize_ai_bot_orders(game, bot_name, game_id=game_id, use_tactical=use_tactical)
    return get_random_bot_orders(game, bot_name)[0]