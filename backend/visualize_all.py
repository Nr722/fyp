import json
import os
from diplomacy.engine.game import Game
from diplomacy.engine.renderer import Renderer

def generate_all_maps(json_filepath, output_dir="phase_maps"):
    os.makedirs(output_dir, exist_ok=True)
    
    with open(json_filepath, 'r') as f:
        log_data = json.load(f)

    # Initialize with the default starting board state (State N-1)
    initial_game = Game()
    current_board_state = {
        "units": {p: initial_game.get_units(p) for p in initial_game.powers},
        "centers": {p: initial_game.get_centers(p) for p in initial_game.powers}
    }

    for index, turn in enumerate(log_data, start=1):
        phase_name = turn.get("phase")
        if not phase_name:
            continue
            
        print(f"Generating map for {index:03d}_{phase_name}...")
        
        game = Game()
        game.phase = phase_name
        
        # 1. Hydrate the board with the PREVIOUS turn's state
        game.clear_units()
        for power, units in current_board_state.get("units", {}).items():
            game.set_units(power, units)
        for power, centers in current_board_state.get("centers", {}).items():
            game.set_centers(power, centers)
            
        # 2. Stage the CURRENT turn's orders to render the arrows
        orders = turn.get("orders", {})
        for power, power_orders in orders.items():
            try:
                game.set_orders(power, power_orders)
            except Exception:
                pass 

        # 3. Render and save
        try:
            renderer = Renderer(game)
            svg_data = renderer.render(incl_abbrev=True)
            output_path = os.path.join(output_dir, f"{index:03d}_{phase_name}.svg")
            
            with open(output_path, "w") as f:
                f.write(svg_data.decode('utf-8') if isinstance(svg_data, bytes) else svg_data)
        except Exception as e:
            print(f"Failed to render {phase_name}: {e}")

        # 4. Update the board state for the NEXT iteration 
        # (The JSON "board" block represents the state AFTER the orders resolve)
        if turn.get("board"):
            current_board_state = turn.get("board")

if __name__ == "__main__":
    log_file = "sim_a4511235_log.json" 
    if os.path.exists(log_file):
        generate_all_maps(log_file)
    else:
        print(f"Error: Could not find {log_file}")