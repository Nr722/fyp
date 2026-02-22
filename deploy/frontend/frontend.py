import streamlit as st
import requests
import base64

API_URL = "http://localhost:8000"

# --- Configuration ---
HUMAN_POWER_DEFAULT = 'FRANCE'

# --- Streamlit App ---
st.set_page_config(page_title="Diplomacy", layout="wide")
st.title("👑 Diplomacy Game")

# --- Game State Initialization ---
if 'game_id' not in st.session_state:
    st.session_state.game_id = None
    st.session_state.human_power = HUMAN_POWER_DEFAULT
    st.session_state.human_orders_submitted = False

def start_new_game(power):
    res = requests.post(f"{API_URL}/game/new", json={"human_power": power})
    if res.status_code == 200:
        data = res.json()
        st.session_state.game_id = data["game_id"]
        st.session_state.human_power = data["human_power"]
        st.session_state.human_orders_submitted = False
        st.success("Started a new game!")
    else:
        st.error("Failed to start a new game.")

if not st.session_state.game_id:
    start_new_game(HUMAN_POWER_DEFAULT)

if not st.session_state.game_id:
    st.stop()

# Fetch current game state
res = requests.get(f"{API_URL}/game/{st.session_state.game_id}/state")
if res.status_code != 200:
    st.error("Failed to fetch game state. The server might have restarted.")
    if st.button("Start New Game"):
        start_new_game(st.session_state.human_power)
        st.rerun()
    st.stop()

game_state = res.json()
current_phase = game_state["phase"]
active_powers = game_state["active_powers"]
all_powers = game_state["powers"]

# --- Sidebar Controls ---
with st.sidebar:
    st.header("Game Controls")

    # Choose human power
    st.subheader("Human Power")
    new_power = st.selectbox(
        "Play as:",
        options=sorted(all_powers),
        index=sorted(all_powers).index(st.session_state.human_power)
        if st.session_state.human_power in all_powers else 0,
    )
    if new_power != st.session_state.human_power:
        st.session_state.human_power = new_power
        st.rerun()

    if st.button("New Game", use_container_width=True):
        start_new_game(st.session_state.human_power)
        st.rerun()

    st.markdown("---")
    st.subheader("Current Phase")
    st.info(f"**{current_phase}**")

# --- Main Content ---

def render_svg_string(svg_string):
    if not svg_string:
        return
    b64 = base64.b64encode(svg_string.encode("utf-8")).decode("utf-8")
    st.write(
        f'<div style="display: flex; justify-content: center;">'
        f'<img src="data:image/svg+xml;base64,{b64}" alt="Diplomacy Board" style="max-width: 100%; height: auto;"/>'
        f'</div>',
        unsafe_allow_html=True
    )

# Display the current board state
st.header("Game Board")
render_svg_string(game_state["map_svg"])

if game_state.get("history_svg"):
    with st.expander("Show Last Turn Adjudication"):
        st.subheader(f"Adjudication Results: {game_state['last_phase_name']}")
        render_svg_string(game_state["history_svg"])

# Display board status summary
st.header("Board Status")
with st.expander("Show Supply Centers and Units", expanded=True):
    all_units = game_state["units"]
    all_centers = game_state["centers"]
    cols = st.columns(4)
    i = 0
    for power_name in sorted(all_powers):
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
if not game_state["is_game_done"]:
    if not st.session_state.human_orders_submitted:
        st.header(f"Enter Orders for {HUMAN_POWER}")
        
        # Fetch possible orders
        orders_res = requests.get(f"{API_URL}/game/{st.session_state.game_id}/orders/possible/{HUMAN_POWER}")
        if orders_res.status_code == 200:
            orders_data = orders_res.json()
            orderable_locs = orders_data["orderable_locations"]
            all_possible_orders = orders_data["all_possible_orders"]
            power_units = orders_data["power_units"]
        else:
            st.error("Failed to fetch possible orders.")
            orderable_locs = []
            all_possible_orders = {}
            power_units = []

        if not orderable_locs:
            st.write("No units to order this phase.")
            st.session_state.human_orders_submitted = True
            st.rerun()
        else:
            phase_type = current_phase[-1] if current_phase else 'M'

            # Dynamically generate input fields for all units or adjustments in orderable_locs
            current_orders = []
            for loc in orderable_locs:
                possible_orders_for_loc = all_possible_orders.get(loc, [])

                # Adjustment phase (builds/removes)
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

                # Movement / Retreat phases
                unit_string = None
                unit_loc_token = None
                for u in power_units:
                    parts = u.split()
                    if len(parts) < 2:
                        continue
                    token = parts[-1]
                    if token == loc:
                        unit_string = u
                        unit_loc_token = token
                        break
                    if token.split('/')[0] == loc:
                        unit_string = u
                        unit_loc_token = token
                        break

                if not unit_string:
                    st.warning(f"Could not determine unit type for {loc}. Skipping.")
                    continue

                unit_type = unit_string.split()[0].replace('*', '')
                loc_for_order = unit_loc_token or loc

                merged_possible = list(dict.fromkeys(
                    (all_possible_orders.get(loc, []) or []) + (all_possible_orders.get(loc_for_order, []) or [])
                ))

                default_order = f"{unit_type} {loc_for_order} H"
                if default_order not in merged_possible:
                    merged_possible.insert(0, default_order)

                label = f"Order for {unit_type} {loc_for_order}:"
                order = st.selectbox(
                    label,
                    options=merged_possible,
                    key=f"order_{HUMAN_POWER}_{loc}_{phase_type}"
                )
                current_orders.append(order)

            # Submit all orders together
            if st.button(f"Submit Orders for {HUMAN_POWER}", use_container_width=True, type="primary"):
                valid_submission = True
                if phase_type == 'A':
                    n_centers = len(game_state["centers"].get(HUMAN_POWER, []))
                    n_units = len(game_state["units"].get(HUMAN_POWER, []))
                    n_builds = n_centers - n_units
                    if n_builds > 0:
                        n_selected_builds = len([o for o in current_orders if o.endswith(' B')])
                        if n_selected_builds > n_builds:
                            st.error(f"Invalid orders: You have {n_builds} builds available but selected {n_selected_builds}. Please WAIVE the excess builds.")
                            valid_submission = False

                if valid_submission:
                    submit_res = requests.post(
                        f"{API_URL}/game/{st.session_state.game_id}/orders",
                        json={"power": HUMAN_POWER, "orders": current_orders}
                    )
                    if submit_res.status_code == 200:
                        st.session_state.human_orders_submitted = True
                        st.success(f"Orders submitted for {HUMAN_POWER}")
                        st.rerun()
                    else:
                        st.error(f"Invalid order submitted: {submit_res.text}")
    else:
        # Human orders in, generate bot orders and process
        st.header("Processing Turn…")
        
        process_res = requests.post(
            f"{API_URL}/game/{st.session_state.game_id}/process",
            json={"human_power": HUMAN_POWER}
        )
        
        if process_res.status_code == 200:
            process_data = process_res.json()
            bot_orders = process_data.get("bot_orders", {})
            for bp, orders in bot_orders.items():
                st.write(f" {bp}: {', '.join(orders) if orders else 'HOLD ALL'}")
                
            st.success(f"Processed {process_data['prev_phase']}. New phase: {process_data['new_phase']}")
            
            # Reset for next turn
            st.session_state.human_orders_submitted = False
            if st.button("Start Next Turn", use_container_width=True):
                st.rerun()
        else:
            st.error(f"Failed to process turn: {process_res.text}")

# --- Chat Engine ---
st.markdown("---")
st.header("💬 Diplomacy Chat")

msg_res = requests.get(f"{API_URL}/game/{st.session_state.game_id}/messages", params={"power": HUMAN_POWER})
if msg_res.status_code == 200:
    messages = msg_res.json().get("messages", [])
else:
    messages = []

conversations = {"GLOBAL": []}
other_powers = [p for p in active_powers if p != HUMAN_POWER]
for p in other_powers:
    conversations[p] = []

for msg in messages:
    if msg["recipient"] == "GLOBAL":
        conversations["GLOBAL"].append(msg)
    else:
        partner = msg["recipient"] if msg["sender"] == HUMAN_POWER else msg["sender"]
        if partner in conversations:
            conversations[partner].append(msg)

tab_names = ["GLOBAL"] + sorted(other_powers)
tabs = st.tabs(tab_names)

for i, target_name in enumerate(tab_names):
    with tabs[i]:
        chat_container = st.container(height=300)
        with chat_container:
            msgs = conversations.get(target_name, [])
            if not msgs:
                st.info(f"Start of conversation in {target_name}.")
            else:
                for msg in msgs:
                    sender_label = msg["sender"]
                    align = "left"
                    bg_color = "#f0f2f6"
                    
                    if msg["sender"] == HUMAN_POWER:
                        sender_label = "You"
                        align = "right" 
                        bg_color = "#e6f3ff"
                    
                    if align == "right":
                        _, msg_col = st.columns([1, 3])
                    else:
                        msg_col, _ = st.columns([3, 1])
                        
                    with msg_col:
                        st.markdown(
                            f"""
                            <div style="
                                background-color: {bg_color};
                                padding: 10px;
                                border-radius: 10px;
                                margin-bottom: 5px;
                                border: 1px solid #ddd;
                            ">
                                <small style="color: #666;"><b>{sender_label}</b> [{msg['phase']}]</small><br>
                                {msg['message']}
                            </div>
                            """,
                            unsafe_allow_html=True
                        )

        with st.form(key=f"chat_form_{target_name}", clear_on_submit=True):
            user_input = st.text_input("Message:", key=f"input_{target_name}", placeholder=f"Message {target_name}...")
            
            if st.form_submit_button("Send"):
                if user_input.strip():
                    send_res = requests.post(
                        f"{API_URL}/game/{st.session_state.game_id}/messages",
                        json={
                            "sender": HUMAN_POWER,
                            "recipient": target_name,
                            "message": user_input,
                            "phase": current_phase
                        }
                    )
                    if send_res.status_code == 200:
                        st.rerun()
                    else:
                        st.error("Failed to send message.")

# --- Game Over ---
if game_state["is_game_done"]:
    st.header("🏁 Game Over")
    winner = game_state["winner"]
    if winner:
        st.success(f"Winner: {', '.join(winner)}")
    else:
        st.info("Draw.")
