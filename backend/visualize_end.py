import json
import os
from diplomacy.engine.game import Game
from diplomacy.engine.renderer import Renderer

# Target phases specifically for the thesis case studies
TARGET_PHASES = {
    "S1902M": "Case_1_Eastern_Collapse_Start",
    "S1904M": "Case_1_Eastern_Collapse_End",
    "F1904M": "Case_2_Western_Dynamism"
}

def generate_maps(json_filepath):
    with open(json_filepath, 'r') as f:
        log_data = json.load(f)

    # Automatically identify the last turn to ensure it's always processed
    last_phase = log_data[-1].get("phase") if log_data else None

    for turn in log_data:
        phase_name = turn.get("phase")
        
        # Check if the phase is a target or the final phase
        if phase_name in TARGET_PHASES or phase_name == last_phase:
            # Append identifier for the final state if not already in targets
            identifier = TARGET_PHASES.get(phase_name, "Final_State")
            
            print(f"Generating map for {phase_name} ({identifier})...")
            
            game = Game()
            game.phase = phase_name
            
            board_state = turn.get("board", {})
            game.clear_units()
            
            for power, units in board_state.get("units", {}).items():
                game.set_units(power, units)
                
            for power, centers in board_state.get("centers", {}).items():
                game.set_centers(power, centers)

            orders = turn.get("orders", {})
            for power, power_orders in orders.items():
                game.set_orders(power, power_orders)

            try:
                renderer = Renderer(game)
                svg_data = renderer.render(incl_abbrev=True)
                
                output_filename = f"map_{identifier}_{phase_name}.svg"
                with open(output_filename, "w") as f:
                    if isinstance(svg_data, bytes):
                        f.write(svg_data.decode('utf-8'))
                    else:
                        f.write(svg_data)
                print(f"Saved {output_filename}")
            except Exception as e:
                print(f"Failed to render {phase_name}: {e}")

if __name__ == "__main__":
    log_file = "sim_c2058746_log.json" 
    
    if os.path.exists(log_file):
        generate_maps(log_file)
    else:
        print(f"Error: Could not find {log_file}")