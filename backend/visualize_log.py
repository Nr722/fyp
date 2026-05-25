import json
import os
from diplomacy.engine.game import Game
from diplomacy.engine.renderer import Renderer

# Target phases specifically for the thesis case studies
TARGET_PHASES = {
    "S1902M": "Case_1_Eastern_Collapse_Start", # Shows Germany moving into MOS
    "S1904M": "Case_1_Eastern_Collapse_End",   # Shows Germany's supported attacks on SEV
    "F1904M": "Case_2_Western_Dynamism"        # Shows the static East vs. the dynamic West
}

def generate_maps(json_filepath):
    with open(json_filepath, 'r') as f:
        log_data = json.load(f)

    for turn in log_data:
        phase_name = turn.get("phase")
        
        if phase_name in TARGET_PHASES:
            print(f"Generating map for {phase_name}...")
            
            game = Game()
            
            # FIX: Explicitly update the phase so the renderer prints the correct text
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
                
                output_filename = f"map_{TARGET_PHASES[phase_name]}_{phase_name}.svg"
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