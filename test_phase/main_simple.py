from diplomacy.engine.game import Game
from diplomacy.utils import exceptions
import os, random, json

# ============================================================================
# MAP VISUALIZATION
# ============================================================================
def save_board_state_json(game, phase_label):
    """Save the board state as JSON for analysis."""
    state = game.get_state()
    filename = f"maps/board_{phase_label}.json"
    
    with open(filename, 'w') as f:
        json.dump(state, f, indent=2)
    
    return state


def show_board(game, phase_label):
    """Render and save the board as an SVG map with units and orders."""
    filename = f"maps/board_{phase_label}.svg"
    
    # Use the built-in renderer with orders and abbreviations
    game.render(incl_orders=True, incl_abbrev=True, output_format='svg', output_path=filename)
    
    print(f" Map saved to: {filename}")
    
    # Also save as JSON
    save_board_state_json(game, phase_label)
    
    # Also print text summary
    all_units = game.get_units()
    all_centers = game.get_centers()
    print("\n📊 Board Status:")
    for power_name in sorted(all_units.keys()):
        units = all_units[power_name]
        centers = all_centers[power_name]
        print(f"  {power_name}: {len(centers)} centers | Units: {', '.join(units) if units else 'None'}")


# ============================================================================
# BOT AI
# ============================================================================
def get_bot_orders(game, bot_name):
    """Pick one random valid order per unit for the bot."""
    all_orders_dict = game.get_all_possible_orders()  # dict: {loc: [orders]} for ALL powers
    orderable_locs = game.get_orderable_locations(bot_name)
    orders = []
    
    for loc in orderable_locs:
        if loc in all_orders_dict and all_orders_dict[loc]:
            # Filter orders to only those that belong to this bot power
            # Orders format: "A/F LOC - DEST" so they start with the unit designation
            bot_valid_orders = [order for order in all_orders_dict[loc] 
                               if order.startswith(('A ', 'F '))]
            if bot_valid_orders:
                orders.append(random.choice(bot_valid_orders))
    
    return orders


# ============================================================================
# MAIN GAME LOOP
# ============================================================================
if __name__ == "__main__":
    # Game setup
    game = Game(map_name='standard')
    human_power = 'FRANCE'
    bot_power = 'ENGLAND'
    
    os.makedirs('maps', exist_ok=True)
    
    print("=" * 60)
    print("DIPLOMACY - SIMPLE GAME")
    print("=" * 60)
    print(f"You are playing as: {human_power}")
    print(f"AI opponent: {bot_power}")
    print("=" * 60)
    
    # Show initial board state
    print("\n Starting new game...")
    show_board(game, "START")
    
    # Game loop
    while not game.is_game_done:
        phase = game.get_current_phase()
        print(f"\n{'='*60}")
        print(f"PHASE: {phase}")
        print(f"{'='*60}")
        
        # Show current state using Game API
        human_units = game.get_units(human_power)
        human_centers = game.get_centers(human_power)
        print(f"\nYour supply centers: {len(human_centers)}")
        print(f"Your units: {human_units if human_units else 'None'}")
        
        # Get orderable locations for this phase
        orderable_locs = game.get_orderable_locations(human_power)
        if not orderable_locs:
            print("No units to order this phase.")
        else:
            print(f"\n Orderable locations: {orderable_locs}")
            
            # Show all possible moves
            print("\n Possible Moves:")
            all_possible_orders = game.get_all_possible_orders()
            for loc in sorted(orderable_locs):
                if loc in all_possible_orders:
                    possible_orders = all_possible_orders[loc]
                    print(f"  {loc}: {', '.join(possible_orders)}")
        
        # Get player orders
        print("\nEnter your orders (one per line, blank line to finish):")
        print("Examples: 'A PAR - BUR', 'F LON - ENG', 'A MAR H', etc.")
        orders = []
        while True:
            line = input("> ").strip().upper()
            if not line:
                break
            orders.append(line)
        
        # Submit player orders
        if orders:
            try:
                game.set_orders(human_power, orders)
                print(f"Your orders set: {orders}")
            except exceptions.GameError as e:
                print(f" Invalid orders: {e}")
                print("  Please try again.")
                continue
        else:
            # If no orders provided, hold all units (game will auto-assign)
            game.set_orders(human_power, [])
            print(" All units holding.")
        
        # Bot plays
        bot_orders_list = get_bot_orders(game, bot_power)
        game.set_orders(bot_power, bot_orders_list)
        print(f" Bot orders: {bot_orders_list}")
        
        # Process the phase
        game.process()
        
        # Show results
        show_board(game, phase)
    
    # Game over
    print(f"\n{'='*60}")
    print(" GAME OVER ")
    print(f"{'='*60}")
    
    # Show final state
    final_units = game.get_units()
    final_centers = game.get_centers()
    print("\nFinal Supply Centers:")
    for power_name in sorted(final_centers.keys()):
        center_count = len(final_centers[power_name])
        print(f"  {power_name}: {center_count} centers")
    
    print(f"\nWinner: {game.get_winner()}")
    print("=" * 60)
