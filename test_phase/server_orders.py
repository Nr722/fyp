import os
import json
from typing import Dict, Any, List
from fastmcp import FastMCP

from diplomacy import Game  # diplomacy python library
from diplomacy.utils.export import to_saved_game_format

app = FastMCP(
    name="Diplomacy Orders Server",
    host="0.0.0.0",
    port=8001,
)

GAME_STATE_PATH = "./game_state.json"
ORDERS_DIR = "./orders"
os.makedirs(ORDERS_DIR, exist_ok=True)


# -------------------------------
# Utility: Load Game
# -------------------------------

def load_game() -> Game:
    """Load diplomacy Game object from stored JSON."""
    if not os.path.exists(GAME_STATE_PATH):
        raise FileNotFoundError("game_state.json not found.")

    with open(GAME_STATE_PATH, "r") as f:
        data = json.load(f)

    game = Game.from_dict(data)
    return game


def save_game(game: Game):
    """Save diplomacy Game object back to JSON."""
    with open(GAME_STATE_PATH, "w") as f:
        json.dump(to_saved_game_format(game), f, indent=2)


# -------------------------------
# TOOL: validate + store orders
# -------------------------------

@app.tool()
def submit_orders(power: str, proposed_orders: Dict[str, str]) -> Dict[str, Any]:
    """
    Validate orders for a given power and store them in ./orders/<POWER>.json

    Parameters:
    - power: e.g., "FRANCE"
    - proposed_orders: dict like {"A PAR": "A PAR - BUR", ...}

    Returns:
    - {"ok": true, "path": "..."}  or
    - {"ok": false, "error": "..."} 
    """

    # Load current game state
    try:
        game = load_game()
    except Exception as e:
        return {"ok": False, "error": f"Failed to load game: {e}"}

    # Get all possible orders and orderable locations
    all_possible = game.get_all_possible_orders()
    orderable_locs = game.get_orderable_locations(power)

    # Validate each order
    errors = []
    for unit_loc, order in proposed_orders.items():
        # Check if this location is orderable by this power
        if unit_loc not in orderable_locs:
            errors.append(f"Location {unit_loc} is not orderable by {power}.")
            continue
        
        # Check if the order is in the list of possible orders for that location
        possible_for_loc = all_possible.get(unit_loc, [])
        if order not in possible_for_loc:
            errors.append(f"Order '{order}' is not valid for {unit_loc}. Valid: {possible_for_loc[:3]}")

    if errors:
        return {"ok": False, "error": " | ".join(errors)}

    # If valid → store JSON
    output_path = os.path.join(ORDERS_DIR, f"{power}.json")
    with open(output_path, "w") as f:
        json.dump(proposed_orders, f, indent=2)

    return {"ok": True, "path": output_path}


# -----------------------------------
# TOOL: fetch valid orders for prompt
# -----------------------------------

@app.tool()
def get_valid_orders(power: str) -> Dict[str, Any]:
    """
    Return all legal orders for a given power, to allow the LLM
    to choose from safe options.
    
    Returns a dict with:
    - orderable_locations: list of locations this power can order
    - possible_orders: dict mapping each location to list of valid orders
    """
    game = load_game()
    orderable_locs = game.get_orderable_locations(power)
    all_possible = game.get_all_possible_orders()
    
    return {
        "orderable_locations": orderable_locs,
        "possible_orders": {loc: all_possible.get(loc, []) for loc in orderable_locs}
    }


# -----------------------------------
# TOOL: get current game phase
# -----------------------------------

@app.tool()
def get_phase() -> str:
    """Return the game's current phase."""
    game = load_game()
    return game.get_current_phase()


# -----------------------------------
# TOOL: overwrite game_state.json
# (optional: used by your engine loop)
# -----------------------------------

# @app.tool()
# def update_game_state(new_state: Dict[str, Any]) -> str:
#     """Allow your Diplomacy engine to push new state to MCP."""
#     with open(GAME_STATE_PATH, "w") as f:
#         json.dump(new_state, f, indent=2)
#     return "Game state updated."


# -------------------------------
# RUN SERVER
# -------------------------------

if __name__ == "__main__":
    print("Starting Diplomacy Orders MCP server on port 8001...")
    app.run(transport="streamable-http")
