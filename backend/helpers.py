"""
Helper functions for the Streamlit Diplomacy app.
"""
import streamlit as st
import os
import base64
import json
from diplomacy.utils.export import to_saved_game_format

def get_map_filename(phase_label):
    """Generates the filename for the map SVG."""
    return f"maps/board_{phase_label}.svg"

def show_board(game, phase_label):
    """Render and save the board as an SVG map with units, orders, and abbreviations."""
    os.makedirs('maps', exist_ok=True)
    
    filename = get_map_filename(phase_label)
    
    # Use the built-in renderer with orders and abbreviations
    game.render(incl_orders=True, incl_abbrev=True, output_path=filename)
    
    # Also save the game state as JSON
    saved_game_path = f"maps/game_{phase_label}.json"
    with open(saved_game_path, 'w') as f:
        json.dump(to_saved_game_format(game), f, indent=2)

def render_svg(svg_file):
    """Render an SVG file in Streamlit."""
    if not os.path.exists(svg_file):
        st.warning(f"Map file not found: {svg_file}")
        return
    with open(svg_file, "r") as f:
        svg_string = f.read()
    
    b64 = base64.b64encode(svg_string.encode("utf-8")).decode("utf-8")
    
    st.write(
        f'<div style="display: flex; justify-content: center;">'
        f'<img src="data:image/svg+xml;base64,{b64}" alt="Diplomacy Board" style="max-width: 100%; height: auto;"/>'
        f'</div>',
        unsafe_allow_html=True
    )
