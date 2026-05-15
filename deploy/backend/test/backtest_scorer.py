import json
import os
import sys
from diplomacy import Game

# Ensure we can import from the backend
sys.path.append(os.getcwd())
from function_tools.tactial_scorer import score_individual_orders

def backtest_scorer(file_path):
    with open(file_path, 'r') as f:
        game_data = json.load(f)
    
    phases = game_data.get('phases', [])
    total_orders_evaluated = 0
    top_1_matches = 0
    top_4_matches = 0
    
    print(f"\n--- Backtesting Scorer on {os.path.basename(file_path)} ---")
    
    for phase_data in phases:
        phase_name = phase_data.get('name')
        # Skip retreat and build phases for tactical movement testing
        if not phase_name.endswith('M'):
            continue
            
        # Create a game object and set its state
        game = Game()
        state = phase_data.get('state', {})
        
        # Manually reconstruct the game state from the JSON
        # This is a simplified version - we set centers and units
        for power, units in state.get('units', {}).items():
            game.set_units(power, units)
        for power, centers in state.get('centers', {}).items():
            game.set_centers(power, centers)
            
        actual_orders = phase_data.get('orders', {})
        
        for power, orders in actual_orders.items():
            if not orders:
                continue
                
            scored_options = score_individual_orders(game, power)
            
            for actual_order in orders:
                # Actual order format: 'A PAR - BUR'
                # We need to find the location (PAR)
                parts = actual_order.split()
                if len(parts) < 2:
                    continue
                loc = parts[1][:3].upper() # PAR
                
                if loc in scored_options:
                    total_orders_evaluated += 1
                    suggested = scored_options[loc] # Top 5
                    suggested_orders = [s['order'] for s in suggested]
                    
                    if actual_order in suggested_orders:
                        top_4_matches += 1
                        if actual_order == suggested_orders[0]:
                            top_1_matches += 1
                    else:
                        print(f"MISS in {phase_name}: {power} played '{actual_order}' but it wasn't in Top 5 suggested: {suggested_orders}")

    if total_orders_evaluated > 0:
        p1 = (top_1_matches / total_orders_evaluated) * 100
        p4 = (top_4_matches / total_orders_evaluated) * 100
        print(f"Results for {os.path.basename(file_path)}:")
        print(f"  Total Orders Checked: {total_orders_evaluated}")
        print(f"  Top 1 Accuracy: {p1:.2f}%")
        print(f"  Top 5 (Recall@5): {p4:.2f}%")
        return total_orders_evaluated, top_1_matches, top_4_matches
    return 0, 0, 0

if __name__ == "__main__":
    print("Starting backtest of tactical scorer on redacted games...")
    game_files = [
        'test/cicero_redacted_games/game_433761_ENGLAND_AG.json',
        'test/cicero_redacted_games/game_433967_ENGLAND_IT.json',
    ]
    
    grand_total = 0
    grand_p1 = 0
    grand_p4 = 0
    
    for gf in game_files:
        if os.path.exists(gf):
            t, p1, p4 = backtest_scorer(gf)
            grand_total += t
            grand_p1 += p1
            grand_p4 += p4
            
    if grand_total > 0:
        print("\n--- GLOBAL RESULTS ---")
        print(f"Overall Top 1 Accuracy: {(grand_p1/grand_total)*100:.2f}%")
        print(f"Overall Top 5 Accuracy: {(grand_p4/grand_total)*100:.2f}%")
