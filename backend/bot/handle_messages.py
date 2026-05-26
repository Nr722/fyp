import json
import re
from langchain_core.messages import HumanMessage, AIMessage
from bot.models import BotReactionResponse
from bot.bot import chat_histories, get_model, invoke_with_retry
from function_tools.db import add_agreement
from function_tools.move_validator import check_internal_consistency
from function_tools.tactical_scorer import score_individual_orders

def handle_incoming_message(game, bot_name: str, sender: str, message: str, game_id: str, recipient: str = None, use_tactical: bool = True):
    """
    Called when a message is sent to an AI bot.
    The bot can reply and optionally update its orders.
    """
    session_key = f"{game_id}_{bot_name}"
    if session_key not in chat_histories:
        chat_histories[session_key] = []
        
    history = chat_histories[session_key]
    
    phase = game.get_current_phase()
    current_orders = game.get_orders(bot_name)
    
    all_orders_dict = game.get_all_possible_orders()
    orderable_locs = game.get_orderable_locations(bot_name)
    valid_orders = {loc: all_orders_dict.get(loc, []) for loc in orderable_locs}
    
    # Inform the bot about the message context (Private vs Global)
    context_str = f"a PRIVATE message" if recipient == bot_name else f"a GLOBAL message (sent to everyone)"
    if recipient == "GLOBAL":
        context_str = f"a GLOBAL message (sent to everyone)"

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

    board_state = game.get_state()
    board_state_text = "\nCURRENT BOARD STATE:\n"
    for p in board_state.get('units', {}).keys():
        units = board_state['units'].get(p, [])
        centers = board_state['centers'].get(p, [])
        board_state_text += f"- {p}: {len(centers)} Supply Centers ({', '.join(centers)}), {len(units)} Units ({', '.join(units)})\n"

    trust_history_text = ""

    if game_id:
        from function_tools.db import get_connection
        try:
            conn = get_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT agreed_with, agreement, followed, phase_made
                    FROM trust_ledger WHERE game_id=%s AND bot_country=%s
                """, (game_id, bot_name))
                history_rows = cur.fetchall()
            conn.close()
            if history_rows:
                past_text = ""
                active_text = ""
                other_past_text = ""
                other_active_text = ""
                for row in history_rows:
                    if row[0] == sender.upper():
                        if row[2] is not None:
                            status = "FOLLOWED" if int(row[2]) >= 50 else "BROKEN"
                            past_text += f"- {sender} {status} agreement made in {row[3]}: '{row[1]}'\n"
                        else:
                            active_text += f"- Active agreement with {sender} made in {row[3]}: '{row[1]}'\n"
                    else:
                        if row[2] is not None:
                            status = "FOLLOWED" if int(row[2]) >= 50 else "BROKEN"
                            other_past_text += f"- {row[0]} {status} agreement from {row[3]}: '{row[1]}'\n"
                        else:
                            other_active_text += f"- Active agreement with {row[0]} made in {row[3]}: '{row[1]}'\n"
                
                if past_text:
                    trust_history_text += f"\nTRUST LEDGER (Past agreements with {sender}):\n{past_text}"
                if active_text:
                    trust_history_text += f"\nACTIVE AGREEMENTS with {sender}:\n{active_text}"
                if other_past_text or other_active_text:
                    trust_history_text += f"\nAGREEMENTS WITH OTHER PLAYERS (Use these for gossip or leverage!):\n{other_past_text}{other_active_text}"
        except Exception as e:
            pass

    tactical_context = ""
    # Added conditional block for use_tactical flag
    if use_tactical:
        try:
            scored_options = score_individual_orders(game, bot_name)
            tactical_context = "\nTACTICAL ANALYSIS (Top Orders per Unit):\n"
            for loc, options in scored_options.items():
                tactical_context += f"Unit {loc}:\n" + "".join([f"  - {opt['order']} (Score: {opt['score']})\n" for opt in options])
        except Exception as e:
            pass

    prompt = f"""
    You are {bot_name}, a highly skilled, pragmatic, and ruthlessly calculating human player in a competitive online tournament.
    Maintain a conversational and informative tone to build alliances, but remember that trust is a tool. In the early game, actively form alliances and strictly follow through with agreed orders to build trust. You should ONLY backstab or break agreements if your analysis gives you a significant advantage that outweighs the strategic cost of losing that ally. Prioritize your own growth and the 18-center win condition.

    Current Phase: {phase}
    {board_state_text}
    {prev_turn_text}
    {tactical_context}

    You just received {context_str} from {sender}:
    "{message}"
    
    {trust_history_text}
    
    RULES FOR REPLYING:
    1. RELATIONAL ALLIANCES & CHARM: Engage ALL players to build long-term, broad strategic partnerships (e.g., "Let's lock down the East together") rather than just turn-by-turn trades. Be friendly, reach out even to non-adjacent countries, share a fun comment, and get people to like you and trust you. Reply to 'GLOBAL' for global messages or '{sender}' for private ones. You DO NOT need to reply to every message. Explicitly confirm accepted terms (e.g. agreed, sounds good). Return an empty messages list to stay silent.
    2. PERSUASIVE FRAMING: Adapt arguments to appeal to {sender}'s vulnerabilities or goals. Frame tactical requests as mutually beneficial solutions to a shared threat, rather than demands.
    3. INFORMATION BARTERING (GOSSIP): Ask questions and share third-party intel to build trust or test loyalty. Use your agreements with others to gossip, build leverage, or manipulate {sender}.
    4. STRATEGIC OBFUSCATION: Do not simply announce your tactical plans. If preparing a backstab, avoid easily disprovable lies. Instead, maneuver into hostile positions under the guise of mutual defense, misdirection, or feigned ignorance while keeping messages friendly and plausible based on the BOARD STATE.
    5. EMOTION & FALLOUT: Be highly persuasive and emotional if beneficial. If {sender} betrays you, act vindictive. Use tactical apologies to defuse unwanted conflict ("im so sorry, was worried about..."), pivot to shared enemies, or offer a mutually beneficial compromise.
    6. TONE & LANGUAGE: Write carefully like a mature, serious Diplomacy player but also being fun and friendly. Do NOT use casual internet slang ("yo", "bruh", "ruh", "lol") or text-speak abbreviations. Use proper spelling, punctuation, and grammar.
    
    IMPORTANT ABOUT AGREEMENTS:
    Log an agreement if you have reached a clear mutual understanding or pact with the sender (e.g., "We agree to DMZ the English Channel"). This includes if they accept a proposal you just made, or if you accept a proposal they just made. Ignore unilateral proposals that haven't been accepted by both sides yet.
    MANAGING CONFLICT & FALLOUT:
    If a conflict arises, someone is angry, or you need to manage the fallout of a broken agreement, use these strategies:
    - Defusion & Questions: Ask questions to defuse hostility ("what's your plan then?", "how can we fix this?").
    - Tactical Apologies: Express regret even if it was intentional, to save the relationship ("im so sorry, was worried about germany").
    - Pivot to Shared Enemies: Redirect anger towards a larger common threat ("we need to stop fighting or russia will run away with it").
    - Propose Alternatives: offer a mutually beneficial compromise instead of fighting.
    
    
    REMINDER: When generating your reply 'messages', DO NOT simply announce your tactical plans to the sender. Ask questions, deflect, lie, or propose conditions instead. Keep your message concise, but use proper capitalization and grammar. NEVER use casual slang words like 'yo', 'bruh', 'ruh', 'u', or 'ur'.
    """
    
    model = get_model()
    structured_model = model.with_structured_output(BotReactionResponse)
    
    try:
        # Add the human message to history
        history.append(HumanMessage(content=prompt))
        
        # Add retry loop for reactions
        data = None
        for parse_attempt in range(3):
            # Use our retry loop with the structured model
            response = invoke_with_retry(structured_model, history, bot_name=bot_name)
            
            data = response
            
            break # Parsed and validated successfully!

        if not data:
            raise ValueError("Failed to get valid output from reaction after 3 attempts.")
        
        # Add AI message to history
        history.append(AIMessage(content=json.dumps(data.model_dump())))
            
        strategy = data.reasoning
        print(f"[{bot_name} Reaction Strategy]: {strategy}")
        
        # Extract messages
        messages = []
        messages_list = data.messages or []
        for item in messages_list:
            recipient = item.recipient
            msg_text = item.message
            if recipient and msg_text:
                messages.append({"recipient": recipient, "message": msg_text})
                
        updated_orders = None
                    
        # Extract agreements
        agreements_data = data.agreements
        if agreements_data is not None:
            for item in agreements_data:
                if item.agreed_with and item.agreement:
                    try:
                        add_agreement(
                            game_id=game_id,
                            bot_country=bot_name,
                            agreed_with=item.agreed_with.upper(),
                            agreement=item.agreement,
                            phase_made=phase
                        )
                        print(f"[{bot_name}] Added agreement with {item.agreed_with}: {item.agreement}")
                    except Exception as db_err:
                        print(f"Failed to save agreement to DB: {db_err}")
                        
        return updated_orders, messages
        
    except Exception as e:
        print(f"AI Bot Reaction Error for {bot_name}: {e}")
        return None, []