"""
Bot AI logic for the Diplomacy game.
"""
import random
import json
import os
import re
from click import prompt
from dotenv import load_dotenv
import os
import json
import google.genai as genai
from models import BotTurnResponse  # Import the model above
from diplomacy.engine.game import Game
load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
chat_sessions = {}

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
        return orders

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
        return orders

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
        return orders

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
    return orders


def get_ai_bot_orders(game, bot_name: str, game_id: str = None):
    all_orders_dict = game.get_all_possible_orders()
    orderable_locs = game.get_orderable_locations(bot_name)
    phase = game.get_current_phase()
    
    if not orderable_locs:
        return []
        
    valid_orders = {loc: all_orders_dict.get(loc, []) for loc in orderable_locs}

    prompt = f"""
    You are an expert Diplomacy player controlling {bot_name}.
    Current Phase: {phase}

    STRICT RULES:
    1. Provide exactly ONE order for every location listed.
    2. Choose ONLY from the 'Valid Options' provided.
    
    Available Locations and Valid Options:
    {json.dumps(valid_orders, indent=2)}
    """
    # Unique key combining the game and the specific bot
    session_key = f"{game_id}_{bot_name}"

    # 2. Check if this bot already has a "brain" session for this game
    if session_key not in chat_sessions:
        print(f"Creating new session for {session_key}")
        chat_sessions[session_key] = client.chats.create(model='gemini-2.5-flash-lite')

    # 3. Retrieve the existing session
    chat = chat_sessions[session_key]

    try:
        # 4. send_message automatically updates the 'history' inside the chat object
        response = chat.send_message(
            message=prompt,
            config={
                'response_mime_type': 'application/json',
                'response_json_schema': BotTurnResponse.model_json_schema(),
            }
        )

        # 1. Get the raw data
        # If .parsed is a dict, we use it. If it's a Pydantic object, we convert to dict.
        data = response.parsed
        if not isinstance(data, dict):
            data = data.model_dump()

        # 2. Access using dictionary keys (Safe for both scenarios)
        strategy = data.get("reasoning", "No reasoning provided.")
        print(f"[{bot_name} Strategy]: {strategy}")

        final_orders = []
        # 3. Handle the 'orders' list safely
        orders_list = data.get("orders", [])
        for item in orders_list:
            # Handle if 'item' is a dict or an object
            loc = item.get("location") if isinstance(item, dict) else item.location
            order_str = item.get("order") if isinstance(item, dict) else item.order
            
            if order_str in valid_orders.get(loc, []):
                final_orders.append(order_str)
            else:
                # Fallback to the first valid order if the AI hallucinated
                if valid_orders.get(loc):
                    final_orders.append(valid_orders[loc][0])

        return final_orders

    except Exception as e:
        print(f"AI Bot Error for {bot_name}: {e}")
        # Use your random fallback
        from bot import get_random_bot_orders
        return get_random_bot_orders(game, bot_name)
    
def get_bot_orders(game, bot_name, bot_type="random", game_id=None):
    if bot_type == "ai" and game_id is not None:
        return get_ai_bot_orders(game, bot_name, game_id=game_id)
    return get_random_bot_orders(game, bot_name)

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

