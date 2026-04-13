import json
import re
from langchain_core.messages import HumanMessage, AIMessage
from bot.models import BotReactionResponse
from bot.bot import chat_histories, get_model, invoke_with_retry

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

    prompt = f"""
    You are an expert Diplomacy player controlling {bot_name}.
    Current Phase: {phase}
    
    You just received {context_str} from {sender}:
    "{message}"
    
    Your current pending orders are:
    {current_orders}
    
    Do you want to reply to this message? If it was a GLOBAL message, you might want to reply to 'GLOBAL'.
    If it was a PRIVATE message, you should reply to '{sender}'.
    
    Do you want to change your orders based on this new information?
    If you want to change your orders, provide the FULL list of updated orders.
    If you do not want to change your orders, omit the 'orders' field.
    
    Available Locations and Valid Options (if you choose to update orders):
    {json.dumps(valid_orders, indent=2)}
    
    IMPORTANT: You MUST respond with a JSON object exactly matching this schema:
    {BotReactionResponse.model_json_schema()}
    """
    
    model = get_model()
    
    try:
        # Add the human message to history
        history.append(HumanMessage(content=prompt))
        
        # Use retry mechanism with exponential backoff
        response = invoke_with_retry(model, history, bot_name=bot_name)
        
        # Parse text
        raw_text = response.content
        if isinstance(raw_text, list):
            raw_text = "".join(item.get("text", "") if isinstance(item, dict) else str(item) for item in raw_text)
        else:
            raw_text = str(raw_text)
            
        match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if match:
            data_dict = json.loads(match.group(0))
        else:
            data_dict = json.loads(raw_text)
            
        data = BotReactionResponse(**data_dict)
        
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
                        
        return updated_orders, messages
        
    except Exception as e:
        print(f"AI Bot Reaction Error for {bot_name}: {e}")
        return None, []
