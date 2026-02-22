import json
import time
import os
from diplomacy import Game
from diplomacy.utils.export import to_saved_game_format
from bot import get_ai_orders_sync

GAME_STATE_PATH = "./game_state.json"

def save_game(game: Game):
    with open(GAME_STATE_PATH, "w") as f:
        json.dump(to_saved_game_format(game), f, indent=2)

def load_game():
    with open(GAME_STATE_PATH, "r") as f:
        data = json.load(f)
    game = Game.from_dict(data)
    return game

# -------------------------------
# MAIN GAME LOOP
# -------------------------------

def main():
    HUMAN_POWER = "FRANCE"
    AI_POWER = "ENGLAND"
    
    # Start a fresh game if state doesn't exist
    try:
        game = load_game()
        print("Loaded existing game.")
    except:
        game = Game()
        save_game(game)
        print("Started new Diplomacy game.")
    
    print(f"\nYou are playing as: {HUMAN_POWER}")
    print(f"AI opponent: {AI_POWER}")
    print(f"Other powers will hold.\n")

    while not game.is_game_done:

        phase = game.get_current_phase()
        print(f"\n=== {phase} ===")

        for power_name, power_obj in game.powers.items():
            if power_obj.is_eliminated():
                continue

            orderable_locs = game.get_orderable_locations(power_name)
            if not orderable_locs:
                continue

            print(f"\n>>> Collecting orders for {power_name}")

            if power_name == HUMAN_POWER:   # human
                orders = []
                all_possible = game.get_all_possible_orders()
                
                print(f"Your orderable locations: {orderable_locs}")
                for loc in orderable_locs:
                    possible_orders = all_possible.get(loc, [])
                    if possible_orders:
                        print(f"\n{loc} options:")
                        for idx, order in enumerate(possible_orders):
                            print(f"  {idx}: {order}")
                        choice = input(f"Enter number for {loc} (or order text): ")
                        try:
                            orders.append(possible_orders[int(choice)])
                        except (ValueError, IndexError):
                            orders.append(choice.strip().upper())
                
                game.set_orders(power_name, orders)
                print(f"✓ Your orders: {orders}")

            elif power_name == AI_POWER:   # LLM power
                print(f"🤖 AI is thinking...")
                ai_result = get_ai_orders_sync(game, power_name)
                
                # Print LLM reasoning/output
                print(f"\n--- AI Agent Output ---")
                print(ai_result.get('raw', 'No output'))
                print(f"--- End AI Output ---\n")
                
                # Try to load orders from file created by MCP server
                orders_file = f"./orders/{power_name}.json"
                orders = []
                if os.path.exists(orders_file):
                    with open(orders_file, "r") as f:
                        orders_dict = json.load(f)
                        # Convert dict to list of order strings
                        orders = list(orders_dict.values())
                    print(f"✓ AI orders loaded from file: {orders}")
                else:
                    print(f"⚠️  No orders file found, AI will hold all units")
                
                game.set_orders(power_name, orders)

            else:   # Other powers - hold all units
                print(f"⏸️  {power_name} holds all units")
                game.set_orders(power_name, [])

        print("\nProcessing phase...")
        game.process()

        save_game(game)
        print("Saved new game state.")

        # Optional: send new state to MCP server
        # call_mcp_update_state(game.to_json())

    print("Game over!")

if __name__ == "__main__":
    main()
