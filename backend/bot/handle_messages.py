import json
import re
from langchain_core.messages import HumanMessage, AIMessage
from bot.models import BotReactionResponse
from bot.bot import chat_histories, get_model, invoke_with_retry, _init_bot_history, _get_common_context
from function_tools.db import add_agreement
from function_tools.move_validator import check_internal_consistency
from function_tools.tactical_scorer import score_individual_orders

def handle_incoming_message(game, bot_name: str, sender: str, message: str, game_id: str, recipient: str = None, use_tactical: bool = True):
    """
    Called when a message is sent to an AI bot.
    The bot can reply and optionally update its orders.
    """
    session_key = f"{game_id}_{bot_name}"
    
    # FIX: Properly initialize the chat history with the bot's system prompt and strategy
    if session_key not in chat_histories:
        _init_bot_history(bot_name, session_key)
        
    history = chat_histories[session_key]
    
    # Get available orders for future logic (if you plan to update orders here)
    all_orders_dict = game.get_all_possible_orders()
    orderable_locs = game.get_orderable_locations(bot_name)
    valid_orders = {loc: all_orders_dict.get(loc, []) for loc in orderable_locs}
    
    # Inform the bot about the message context (Private vs Global)
    context_str = f"a PRIVATE message" if recipient == bot_name else f"a GLOBAL message (sent to everyone)"
    if recipient == "GLOBAL":
        context_str = f"a GLOBAL message (sent to everyone)"

    # FIX: Reuse the common context generator to avoid redundant code
    phase, board_state_text, prev_turn_text, _, tactical_context = _get_common_context(game, bot_name, game_id, include_tactical=use_tactical)

    # Custom trust history text tailored specifically for the SENDER of this message
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
                            if int(row[2]) < 50:
                                past_text += f"CRITICAL: {sender} recently BETRAYED you by breaking this agreement: '{row[1]}'. Act guarded, demand reparations, or express anger. Do NOT trust them easily.\n"
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

    # FIX: Streamlined prompt that relies on the system prompt for the main rules
    prompt = f"""Current Phase: {phase}
{board_state_text}
{prev_turn_text}
{tactical_context}

[COMMUNICATION EVENT]
You just received {context_str} from {sender}:
"{message}"

{trust_history_text}

INSTRUCTIONS FOR THIS REPLY:
1. RELATIONAL ALLIANCES: Reply to '{sender}' (private) or 'GLOBAL'. Explicitly confirm accepted terms, or return an empty messages list to stay silent.
2. AGREEMENTS: Only log an agreement if a mutual pact is firmly reached.

Formulate your reaction, log any confirmed agreements, and output your response.

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