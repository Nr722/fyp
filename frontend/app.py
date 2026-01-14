import streamlit as st
import os
from diplomacy.engine.game import Game
try:
    # When running from project root: `streamlit run frontend/app.py`
    from frontend.helpers import show_board, render_svg, get_map_filename
    from frontend.bot import get_bot_orders
    from frontend.viz import generate_history_svg
except ModuleNotFoundError:
    # When running from inside the folder: `cd frontend && streamlit run app.py`
    from helpers import show_board, render_svg, get_map_filename
    from bot import get_bot_orders
    from viz import generate_history_svg

# --- Configuration ---
# Change this to play as a different power; all others will be bots.
HUMAN_POWER_DEFAULT = 'FRANCE'

# --- Streamlit App ---
st.set_page_config(page_title="Diplomacy", layout="wide")
st.title("👑 Diplomacy Game")

# --- Game State Initialization ---
if 'game' not in st.session_state:
    st.session_state.game = Game(map_name='standard')
    st.session_state.human_power = HUMAN_POWER_DEFAULT
    st.session_state.human_orders_submitted = False
    # Render initial map with names and orders
    show_board(st.session_state.game, "START")

game = st.session_state.game

# Ensure a map exists for the current phase before rendering
current_phase = game.get_current_phase()
map_path = get_map_filename(current_phase)
if not os.path.exists(map_path):
    show_board(game, current_phase)

# Compute active powers list
active_powers = [p for p, data in game.powers.items() if not data.is_eliminated()]

# --- Sidebar Controls ---
with st.sidebar:
    st.header("Game Controls")

    # Choose human power
    st.subheader("Human Power")
    st.session_state.human_power = st.selectbox(
        "Play as:",
        options=sorted(list(game.powers.keys())),
        index=sorted(list(game.powers.keys())).index(st.session_state.human_power)
        if st.session_state.human_power in game.powers else 0,
    )

    if st.button("New Game", use_container_width=True):
        st.session_state.game = Game(map_name='standard')
        st.session_state.human_orders_submitted = False
        # Keep the selected human power
        game = st.session_state.game
        show_board(game, "START")
        st.success("Started a new game!")
        st.rerun()

    st.markdown("---")
    st.subheader("Current Phase")
    st.info(f"**{game.get_current_phase()}**")

# --- Main Content ---

# Display the current board state
st.header("Game Board")
render_svg(get_map_filename(game.get_current_phase()))

if game.get_phase_history():
    with st.expander("Show Last Turn Adjudication"):
        last_phase_name = list(game.get_phase_history())[-1].name
        hist_path = f"maps/history_{last_phase_name}.svg"
        if not os.path.exists(hist_path):
             generate_history_svg(game, hist_path)
        
        st.subheader(f"Adjudication Results: {last_phase_name}")
        render_svg(hist_path)


# Display board status summary
st.header("Board Status")
with st.expander("Show Supply Centers and Units", expanded=True):
    all_units = game.get_units()
    all_centers = game.get_centers()
    cols = st.columns(4)
    i = 0
    for power_name in sorted(game.powers.keys()):
        if power_name in active_powers:
            units = all_units.get(power_name, [])
            centers = all_centers.get(power_name, [])
            with cols[i % 4]:
                st.markdown(f"**{power_name}**")
                st.markdown(f"{len(centers)} centers | {len(units)} units")
            i += 1

st.markdown("---")

# --- Orders (Human only) ---
HUMAN_POWER = st.session_state.human_power
if not game.is_game_done:
    if not st.session_state.human_orders_submitted:
        st.header(f"Enter Orders for {HUMAN_POWER}")
        orderable_locs = game.get_orderable_locations(HUMAN_POWER)

        if not orderable_locs:
            st.write("No units to order this phase.")
            st.session_state.human_orders_submitted = True
            st.rerun()
        else:
            all_possible_orders = game.get_all_possible_orders()
            power_units = game.get_units(HUMAN_POWER)
            phase = game.get_current_phase()
            phase_type = phase[-1] if phase else 'M'

            # Dynamically generate input fields for all units or adjustments in orderable_locs
            current_orders = []
            for loc in orderable_locs:
                possible_orders_for_loc = all_possible_orders.get(loc, [])

                # Adjustment phase (builds/removes) — there may be no existing unit at the location
                if phase_type == 'A':
                    if not possible_orders_for_loc:
                        st.warning(f"No adjustment options available for {loc}. Skipping.")
                        continue
                    label = f"Adjustment for {loc}:"
                    order = st.selectbox(
                        label,
                        options=possible_orders_for_loc,
                        key=f"order_{HUMAN_POWER}_{loc}_{phase_type}"
                    )
                    current_orders.append(order)
                    continue

                # Movement / Retreat phases: match an existing unit at the location
                # Locations may include coast qualifiers (e.g. 'SPA/NC'), so match by base token
                unit_string = None
                unit_loc_token = None
                for u in power_units:
                    parts = u.split()
                    if len(parts) < 2:
                        continue
                    token = parts[-1]
                    # Exact match (including coast)
                    if token == loc:
                        unit_string = u
                        unit_loc_token = token
                        break
                    # Match base (before '/') to handle e.g. 'SPA' vs 'SPA/NC'
                    if token.split('/')[0] == loc:
                        unit_string = u
                        unit_loc_token = token
                        break

                if not unit_string:
                    st.warning(f"Could not determine unit type for {loc}. Skipping.")
                    continue

                unit_type = unit_string.split()[0].replace('*', '')
                # Use the unit's precise location token when forming a default HOLD order
                loc_for_order = unit_loc_token or loc

                # Merge possible orders keyed by both the simple loc and the precise token
                merged_possible = list(dict.fromkeys(
                    (all_possible_orders.get(loc, []) or []) + (all_possible_orders.get(loc_for_order, []) or [])
                ))

                default_order = f"{unit_type} {loc_for_order} H"
                if default_order not in merged_possible:
                    merged_possible.insert(0, default_order)

                # Label for the input field
                label = f"Order for {unit_type} {loc_for_order}:"

                # Create input field for the order
                order = st.selectbox(
                    label,
                    options=merged_possible,
                    key=f"order_{HUMAN_POWER}_{loc}_{phase_type}"
                )
                current_orders.append(order)

            # Submit all orders together
            if st.button(f"Submit Orders for {HUMAN_POWER}", use_container_width=True, type="primary"):
                try:
                    game.set_orders(HUMAN_POWER, current_orders)
                    st.session_state.human_orders_submitted = True
                    st.success(f"Orders submitted for {HUMAN_POWER}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Invalid order submitted: {e}")
    else:
        # Human orders in, generate bot orders and process
        st.header("Processing Turn…")
        bot_powers = [p for p in active_powers if p != HUMAN_POWER]
        for bp in bot_powers:
            try:
                bot_orders = get_bot_orders(game, bp)
                game.set_orders(bp, bot_orders)
                st.write(f"🤖 {bp}: {', '.join(bot_orders) if bot_orders else 'HOLD ALL'}")
            except Exception as e:
                st.warning(f"Bot {bp} failed to set orders: {e}")

        prev_phase = game.get_current_phase()
        game.process()

        # Render and show the new phase map (with names & orders)
        show_board(game, game.get_current_phase())
        st.success(f"Processed {prev_phase}. New phase: {game.get_current_phase()}")

        # Reset for next turn
        st.session_state.human_orders_submitted = False
        if st.button("Start Next Turn", use_container_width=True):
            st.rerun()

# --- Game Over ---
if game.is_game_done:
    st.header("🏁 Game Over")
    winner = game.get_winner()
    if winner:
        st.success(f"Winner: {', '.join(winner)}")
    else:
        st.info("Draw.")
