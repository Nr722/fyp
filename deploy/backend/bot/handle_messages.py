import json
import re
from langchain_core.messages import HumanMessage, AIMessage
from bot.models import BotReactionResponse
from bot.bot import chat_histories, get_model, invoke_with_retry
from bot.db import add_agreement
from function_tools.move_validator import check_internal_consistency

def handle_incoming_message(game, bot_name: str, sender: str, message: str, game_id: str, recipient: str = None):
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
        from bot.db import get_connection
        try:
            conn = get_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT agreed_with, agreement, followed, phase_made
                    FROM trust_ledger WHERE game_id=%s AND bot_country=%s AND agreed_with=%s AND followed IS NOT NULL
                """, (game_id, bot_name, sender.upper()))
                history_rows = cur.fetchall()
            conn.close()
            if history_rows:
                trust_history_text = f"\nTRUST LEDGER (Past agreements with {sender} and whether they followed them):\n"
                for row in history_rows:
                    status = "FOLLOWED" if row[2] else "BROKEN"
                    trust_history_text += f"- {sender} {status} agreement made in {row[3]}: '{row[1]}'\n"
        except Exception as e:
            pass

    prompt = f"""
    You are {bot_name}, a pragmatic, highly competitive human player in an online tournament.
    You type quickly using lowercase, abbreviations, and sentence fragments (e.g., "rum", "east med", "bounce", "dmz"). Maintain a confident, unapologetic, and direct tone. Build temporary alliances while aggressively seeking your 18-center win condition.

    Current Phase: {phase}
    {board_state_text}
    {prev_turn_text}

    You just received {context_str} from {sender}:
    "{message}"
    
    {trust_history_text}
    
    RULES FOR REPLYING:
    1. STRATEGIC COMMUNICATION: Reply only when it advances your position. Use brief, competitive responses. Reply to 'GLOBAL' for global messages or '{sender}' for private ones.
    2. SECRECY & MISDIRECTION: Unilaterally declaring your own strict intentions ruins your advantage. Ask questions, float conditions, or lie. NEVER just announce "I am taking X."
    3. BOARD AWARENESS: Ground all statements and proposals strictly in the reality of the CURRENT BOARD STATE.
    4. SYNTAX & VALIDITY: If you update orders, match the 'Valid Options' exactly. Ensure convoys have matching fleet orders, and supported units are executing the exact supported move.
    5. COMMUNICATION STYLE:
    - Brevity: Use short fragments and lowercase text.
    - Inquiry: Ask them about their plans instead of dictating your own ("whats the play?", "u taking serbia?").
    - Confidence: Speak decisively without offering apologies.

    IMPORTANT ABOUT AGREEMENTS:
    Log an agreement ONLY if the message from {sender} explicitly proposed it AND you are explicitly ACCEPTING it now. Log defined mutual pacts (e.g., "We agree to DMZ the English Channel"). Do ignore unilateral proposals you are merely suggesting.
    
    Do you want to change your orders based on this new information?
    If you want to change your orders, provide the FULL list of updated orders.
    If you do not want to change your orders, omit the 'orders' field.
    
    Available Locations and Valid Options (if you choose to update orders):
    {json.dumps(valid_orders, indent=2)}
    
    REMINDER: When generating your reply 'messages', DO NOT simply announce your updated orders to the sender. Ask questions, deflect, lie, or propose conditions instead.
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
            
            # Check for internal consistency in updated orders
            if data and data.orders:
                temp_orders = [o.order for o in data.orders if o.order]
                consistency_errors = check_internal_consistency(temp_orders)
                if consistency_errors:
                    err_str = " ".join(consistency_errors)
                    print(f"[{bot_name} Reaction] Consistency failure: {err_str}")
                    history.append(AIMessage(content=json.dumps(data.model_dump())))
                    history.append(HumanMessage(content=f"Your proposed new orders failed validation: {err_str} Fix these errors and try again."))
                    data = None
                    continue

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
                
        # Extract updated orders if any
        updated_orders = None
        orders_data = data.orders
        if orders_data is not None:
            updated_orders = []
            for item in orders_data:
                loc = item.location
                order_str = item.order
                
                if loc and order_str and order_str in valid_orders.get(loc, []):
                    updated_orders.append(order_str)
                elif loc and valid_orders.get(loc):
                    updated_orders.append(valid_orders[loc][0])
                    
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
