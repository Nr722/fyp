"""
Bot AI logic for the Diplomacy game.
"""
import random
import json
import os
import re
import time
from click import prompt
from dotenv import load_dotenv
import os
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage
from models import BotTurnResponse, BotReactionResponse  # Import the model above
from diplomacy.engine.game import Game
load_dotenv()

# Dictionary to store chat histories for each bot in each game
chat_histories = {}

def get_model(model_name="models/gemini-3.1-flash-lite-preview"):
    # Note: Gemma models currently do not support JSON mode or structured outputs via the API.
    # We use a standard chat model and will handle the parsing manually if needed, 
    # or use a model that does support these features.
    return ChatGoogleGenerativeAI(model=model_name, google_api_key=os.getenv("GEMINI_API_KEY"))

def invoke_with_retry(model, history, max_retries=4, initial_delay=5, bot_name="Bot"):
    """Invokes the model with exponential backoff for RateLimit errors."""
    for attempt in range(max_retries):
        try:
            return model.invoke(history)
        except Exception as e:
            err_msg = str(e).lower()
            if "429" in err_msg or "rate limit" in err_msg or "quota" in err_msg or "resource_exhausted" in err_msg:
                if attempt < max_retries - 1:
                    delay = initial_delay * (2 ** attempt)
                    
                    # Gemini specifically tells us how long to wait ("Please retry in 45.44s")
                    match = re.search(r'retry in ([0-9.]+)s', err_msg)
                    if match:
                        try:
                            required_delay = float(match.group(1))
                            # Add a 2 second buffer to ensure we clear the limit window
                            delay = max(delay, required_delay + 2.0)
                        except ValueError:
                            pass
                            
                    # Use a very specific prefix that is hard to miss
                    print(f"DEBUG_TPM_LIMIT|{bot_name}|{delay:.1f}|{attempt + 1}")
                    time.sleep(delay)
                    continue
            raise e

def _phase_type(game):
    phase = game.get_current_phase() or ''
    return phase[-1] if phase else 'M'

def get_random_bot_orders(game, bot_name):
    """Generate simple bot orders per phase type.

    - Movement (M): random valid order per unit, default HOLD when needed.
    - Retreats (R): prefer a retreat move; fallback to disband if only that is available.
    - Adjustments (A): prefer BUILD/REMOVE choices; fallback to WAIVE if needed.
    """
    all_orders_dict = game.get_all_possible_orders()
    orderable_locs = game.get_orderable_locations(bot_name)
    orders = []
    phase_t = _phase_type(game)

    if not orderable_locs:
        return orders, []

    if phase_t == 'M':
        power_units = game.get_units(bot_name)
        for loc in orderable_locs:
            possible = all_orders_dict.get(loc, [])
            if not possible:
                continue
            unit_at_loc = next((u for u in power_units if u.endswith(f" {loc}")), None)
            if unit_at_loc:
                unit_type = unit_at_loc.split()[0].replace('*', '')
                candidates = [o for o in possible if o.startswith(f"{unit_type} {loc}")]
                if candidates:
                    orders.append(random.choice(candidates))
                else:
                    orders.append(f"{unit_type} {loc} H")
        return orders, []

    if phase_t == 'R':
        # Retreats: options typically include moves and a disband option (e.g., 'D')
        for loc in orderable_locs:
            possible = all_orders_dict.get(loc, [])
            if not possible:
                continue
            # Prefer a retreat move (contains ' - ') over disband (often ends with ' D' or equals 'D')
            moves = [o for o in possible if ' - ' in o]
            if moves:
                orders.append(random.choice(moves))
            else:
                # Fallback: pick any valid option (likely disband)
                orders.append(random.choice(possible))
        return orders, []

    # Adjustments 'A'
    for loc in orderable_locs:
        possible = all_orders_dict.get(loc, [])
        if not possible:
            continue
        builds = [o for o in possible if o.startswith('BUILD')]
        removes = [o for o in possible if o.startswith('REMOVE')]
        waives = [o for o in possible if o.startswith('WAIVE') or o == 'WAIVE']
        if builds:
            orders.append(random.choice(builds))
        elif removes:
            orders.append(random.choice(removes))
        elif waives:
            orders.append(random.choice(waives))
        else:
            # Unknown/edge options; pick something
            orders.append(random.choice(possible))
    return orders, []


def get_ai_bot_orders(game, bot_name: str, game_id: str = None):
    all_orders_dict = game.get_all_possible_orders()
    orderable_locs = game.get_orderable_locations(bot_name)
    phase = game.get_current_phase()
    
    if not orderable_locs:
        return [], []
        
    valid_orders = {loc: all_orders_dict.get(loc, []) for loc in orderable_locs}

    prompt = f"""
    You are an expert Diplomacy player controlling {bot_name}.
    Current Phase: {phase}

    STRICT RULES:
    1. Provide exactly ONE order for every location listed.
    2. Choose ONLY from the 'Valid Options' provided.
    3. If you want to collaborate with other players, you can include messages to them. But you MUST still provide your orders based on the current game state.    
    Available Locations and Valid Options:
    {json.dumps(valid_orders, indent=2)}

    IMPORTANT: You MUST respond with a JSON object exactly matching this schema:
    {BotTurnResponse.model_json_schema()}
    """
    # Unique key combining the game and the specific bot
    session_key = f"{game_id}_{bot_name}"

    # Initialize chat history if not exists
    if session_key not in chat_histories:
        print(f"Creating new history for {session_key}")
        chat_histories[session_key] = []

    history = chat_histories[session_key]
    model = get_model()
    
    try:
        # Add the prompt to history
        history.append(HumanMessage(content=prompt))
        
        # Use retry mechanism with exponential backoff
        response = invoke_with_retry(model, history, bot_name=bot_name)
        
        # Parse the response text
        raw_text = response.content
        match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if match:
            data_dict = json.loads(match.group(0))
        else:
            data_dict = json.loads(raw_text)
            
        data = BotTurnResponse(**data_dict)
        
        # Add AI message to history
        history.append(AIMessage(content=json.dumps(data.model_dump())))

        strategy = data.reasoning
        print(f"[{bot_name} Strategy]: {strategy}")

        final_orders = []
        # Access using object attributes
        orders_data = data.orders or []
        
        for item in orders_data:
            loc = item.location
            order_str = item.order
            
            if loc and order_str and order_str in valid_orders.get(loc, []):
                final_orders.append(order_str)
            elif loc and valid_orders.get(loc):
                # Fallback to the first valid order if the specific one is wrong
                final_orders.append(valid_orders[loc][0])

        messages = []
        messages_list = data.messages or []
        for item in messages_list:
            recipient = item.recipient
            message = item.message
            if recipient and message:
                messages.append({"recipient": recipient, "message": message})

        return final_orders, messages

    except Exception as e:
        print(f"AI Bot Error for {bot_name}: {e}")
        # Use your random fallback
        from bot import get_random_bot_orders
        return get_random_bot_orders(game, bot_name)
    
def get_bot_orders(game, bot_name, bot_type="random", game_id=None):
    if bot_type == "ai" and game_id is not None:
        return get_ai_bot_orders(game, bot_name, game_id=game_id)
    return get_random_bot_orders(game, bot_name)

def handle_incoming_message(game, bot_name: str, sender: str, message: str, game_id: str, recipient: str = None):
    """
    Called when a message is sent to an AI bot.
    The bot can reply and optionally update its orders.
    """
    session_key = f"{game_id}_{bot_name}"
    if session_key not in chat_histories:
        # If the bot hasn't been initialized yet, we can't really react properly,
        # but we could initialize it. For now, let's just initialize it.
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

if __name__ == "__main__":
    from diplomacy.engine.game import Game

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print(" Error: GEMINI_API_KEY not found in environment.")
    else:
        print(" API Key found. Initializing test game...")
        
        # 1. Create a real game instance for the test
        test_game = Game(map_name='standard')
        test_bot = "FRANCE"
        
        print(f" Requesting AI orders for {test_bot}...")
        
        try:
            # 2. Call the function with the instance
            orders = get_ai_bot_orders(test_game, game_id="test_game", bot_name=test_bot)
            
            print("\n--- Test Results ---")
            print(f"Status: Success")
            print(f"Orders received: {orders}")
        except Exception as e:
            print(f"\n--- Test Failed ---")
            print(f"Error Type: {type(e).__name__}")
            print(f"Error Message: {e}")

