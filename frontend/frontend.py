import streamlit as st
import requests
import base64
import time

import os
from dotenv import load_dotenv

load_dotenv()

# API_URL = os.getenv("API_URL", "http://localhost:8000")
API_URL = "https://sunny-sparkle-backend.up.railway.app"
# API_URL = "https://sunny-sparkle-dev.up.railway.app"

def get_headers():
    if 'token' in st.session_state and st.session_state.token:
        return {"Authorization": f"Bearer {st.session_state.token}"}
    return {}

def check_rate_limits():
    """Checks for rate limit events from the backend and displays them as warnings."""
    if 'last_rate_limit_check' not in st.session_state:
        st.session_state.last_rate_limit_check = time.time()
        
    try:
        res = requests.get(f"{API_URL}/game/{st.session_state.game_id}/rate-limits", headers=get_headers())
        if res.status_code == 200:
            events = res.json().get("events", [])
            # Filter for events that happened after our last check
            new_events = [e for e in events if e.get('timestamp', 0) > st.session_state.last_rate_limit_check]
            
            for event in new_events:
                st.toast(
                    f" Rate limit hit for {event['bot_name']}! Retrying in {event['delay']}s (Attempt {event['attempt']})",
                    icon="⏳"
                )
            
            if new_events:
                st.session_state.last_rate_limit_check = time.time()
    except Exception:
        pass

# --- Configuration ---
HUMAN_POWER_DEFAULT = 'RANDOM'

# --- Streamlit App ---
st.set_page_config(page_title="Diplomacy", layout="wide")

# --- Login Logic ---
def login():
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    
    if 'token' not in st.session_state:
        st.session_state.token = None

    if not st.session_state.logged_in:
        st.title("Diplomacy Login")
        
        admin_username = os.getenv("APP_USERNAME")
        admin_password = os.getenv("APP_PASSWORD")

        if not admin_username or not admin_password:
            st.error("Authentication system not configured. Please set APP_USERNAME and APP_PASSWORD in the environment variables.")
            st.stop()

        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Login")
            
            if submit:
                if username == admin_username and password == admin_password:
                    # Fetch JWT Token from backend
                    try:
                        token_res = requests.post(f"{API_URL}/token", data={"username": username, "password": password})
                        if token_res.status_code == 200:
                            st.session_state.token = token_res.json()["access_token"]
                            st.session_state.logged_in = True
                            st.success("Logged in successfully!")
                            st.rerun()
                        else:
                            st.error(f"Backend authentication failed: {token_res.text}")
                    except Exception as e:
                        st.error(f"Error connecting to backend: {e}")
                else:
                    st.error("Invalid username or password")
        st.stop()

login()

st.title(" Diplomacy Game")

# --- Game State Initialization ---
if 'game_id' not in st.session_state:
    st.session_state.game_id = None
    st.session_state.human_power = HUMAN_POWER_DEFAULT
    st.session_state.human_orders_submitted = False
    st.session_state.negotiation_phase_ended = False
    st.session_state.last_seen_messages = 0
    st.session_state.read_counts = {}

def start_new_game(power, num_ai_bots=6):
    res = requests.post(f"{API_URL}/game/new", json={"human_power": power, "num_ai_bots": num_ai_bots}, headers=get_headers())
    if res.status_code == 200:
        data = res.json()
        st.session_state.game_id = data["game_id"]
        st.session_state.human_power = data["human_power"]
        st.session_state.human_orders_submitted = False
        st.session_state.negotiation_phase_ended = False
        st.session_state.last_seen_messages = 0
        st.session_state.read_counts = {}
        st.session_state.ai_powers = data.get("ai_powers", [])
        st.success(f"Started a new game! Bots: {', '.join(st.session_state.ai_powers) if st.session_state.ai_powers else 'None'}")
    else:
        st.error(f"Failed to start a new game: {res.text}")

if not st.session_state.game_id:
    start_new_game(HUMAN_POWER_DEFAULT, 6)

if not st.session_state.game_id:
    st.stop()

# Check for any rate limit events from the last operation
check_rate_limits()

# Debug: Fake Rate Limit Button
# if st.sidebar.button("Debug: Test Rate Limit Popup"):
#     requests.post(f"{API_URL}/game/{st.session_state.game_id}/test-rate-limit", headers=get_headers())
#     st.rerun()

# if st.sidebar.button("Debug: Clear Rate Limit History"):
#     requests.post(f"{API_URL}/game/{st.session_state.game_id}/clear-rate-limits", headers=get_headers())
#     st.session_state.last_rate_limit_check = time.time()
#     st.success("Cleared")

# Fetch current game state
res = requests.get(f"{API_URL}/game/{st.session_state.game_id}/state", headers=get_headers())
if res.status_code != 200:
    st.error("Failed to fetch game state. The server might have restarted.")
    if st.button("Start New Game"):
        start_new_game(st.session_state.human_power, st.session_state.get("num_ai_bots", 6))
        st.rerun()
    st.stop()

game_state = res.json()
current_phase = game_state["phase"]
active_powers = game_state["active_powers"]
all_powers = game_state["powers"]

# --- Sidebar Controls ---
with st.sidebar:
    st.header("Game Controls")

    # View or Swap human power in the current game
    st.subheader("Current Game View")
    new_power = st.selectbox(
        "Play as:",
        options=sorted(all_powers),
        index=sorted(all_powers).index(st.session_state.human_power)
        if st.session_state.human_power in all_powers else 0,
    )
    if new_power != st.session_state.human_power:
        st.session_state.human_power = new_power
        st.rerun()

    st.markdown("---")
    st.subheader("Start New Game")
    new_game_power = st.selectbox(
        "Starting Power:",
        options=["RANDOM"] + sorted(all_powers)
    )
    num_ai_bots = st.slider("Number of AI Bots", min_value=0, max_value=6, value=st.session_state.get("num_ai_bots", 6))
    st.session_state.num_ai_bots = num_ai_bots

    if st.button("Start New Game", use_container_width=True):
        start_new_game(new_game_power, num_ai_bots)
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

# Timeline Feature
st.header("Game Board Timeline")
past_phases = game_state.get("past_phases", [])
current_phase_label = f"{game_state.get('phase', 'Present')} (Current Phase)"
if past_phases:
    timeline_options = past_phases + [current_phase_label]
    selected_time = st.selectbox(
        "View Board History:", 
        options=timeline_options,
        index=len(timeline_options) - 1, # Default: Present
        key="timeline_select"
    )
    
    if selected_time == current_phase_label:
        render_svg_string(game_state["map_svg"])
    else:
        # Fetch historical map for selected_time
        try:
            hist_res = requests.get(f"{API_URL}/game/{st.session_state.game_id}/history/{selected_time}", headers=get_headers())
            if hist_res.status_code == 200:
                hist_svg = hist_res.json().get("map_svg")
                st.info(f"Viewing historical map for {selected_time}. Orders shown are the orders submitted during that phase.")
                render_svg_string(hist_svg)
            else:
                st.error("Failed to load historical timeline map.")
        except Exception as e:
            st.error(f"Error fetching historical map: {e}")
else:
    # If no past phases yet, just show present map
    st.header("Game Board")
    render_svg_string(game_state["map_svg"])


# Legacy Last Turn Expander (optional, removed to avoid clutter, using timeline instead)
# if game_state.get("history_svg"):
#     with st.expander("Show Last Turn Adjudication"):
#         st.subheader(f"Adjudication Results: {game_state['last_phase_name']}")
#         render_svg_string(game_state["history_svg"])

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
        orders_res = requests.get(f"{API_URL}/game/{st.session_state.game_id}/orders/possible/{HUMAN_POWER}", headers=get_headers())
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

            if not st.session_state.negotiation_phase_ended:
                st.write("### Diplomacy Phase")
                st.info("Negotiate with other players. When you are ready, end the negotiation phase to draft your orders.")
                if st.button("End Negotiation Phase", use_container_width=True, type="primary"):
                    st.session_state.negotiation_phase_ended = True
                    st.rerun()

            if st.session_state.negotiation_phase_ended:
                st.write("### Order Phase")
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
                if st.button(f"Submit Orders / Lock In", use_container_width=True, type="primary"):
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
                            json={"power": HUMAN_POWER, "orders": current_orders},
                            headers=get_headers()
                        )
                        if submit_res.status_code == 200:
                            st.session_state.human_orders_submitted = True
                            st.success(f"Orders submitted for {HUMAN_POWER}")
                            st.rerun()
                        else:
                            st.error(f"Invalid order submitted: {submit_res.text}")
    else:
        # Human orders in, generate bot orders and process
        with st.status("Processing Turn...", expanded=True) as status:
            st.write("Gathering orders from all other players...")
            process_res = requests.post(
                f"{API_URL}/game/{st.session_state.game_id}/process",
                json={"human_power": HUMAN_POWER, "phase": current_phase},
                headers=get_headers()
            )
            
            if process_res.status_code == 200:
                status.update(label="Turn Processed!", state="complete", expanded=False)
                process_data = process_res.json()
                bot_orders = process_data.get("bot_orders", {})
                for bp, orders in bot_orders.items():
                    st.write(f" {bp}: {', '.join(orders) if orders else 'HOLD ALL'}")
                    
                st.success(f"Processed {process_data['prev_phase']}. New phase: {process_data['new_phase']}")
                
                # Reset for next turn
                st.session_state.human_orders_submitted = False
                st.session_state.negotiation_phase_ended = False
                if st.button("Start Next Turn", use_container_width=True):
                    st.rerun()
            else:
                status.update(label="Process Failed", state="error")
                st.error(f"Failed to process turn: {process_res.text}")

# --- Chat Engine ---
st.markdown("---")
col1, col2 = st.columns([4, 1])
with col1:
    st.header("💬 Diplomacy Chat")
with col2:
    if st.button("🔄 Refresh Messages", use_container_width=True):
        st.rerun()

# Define the fragment. It will rerun independently every 15 seconds.
@st.fragment(run_every="15s")
def render_chat():
    HUMAN_POWER = st.session_state.human_power
    msg_res = requests.get(f"{API_URL}/game/{st.session_state.game_id}/messages", params={"power": HUMAN_POWER}, headers=get_headers())
    
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
    current_tab = st.session_state.get("chat_tab_selector", "GLOBAL")
    st.session_state.read_counts[current_tab] = len(conversations.get(current_tab, []))

    unread_counts = {}
    for t in tab_names:
        total_msgs = len(conversations.get(t, []))
        read_msgs = st.session_state.read_counts.get(t, 0)
        unread = total_msgs - read_msgs
        unread_counts[t] = unread if unread > 0 else 0

    current_msg_count = len(messages)
    if current_msg_count > st.session_state.get("last_seen_messages", 0):
        new_msgs = messages[st.session_state.get("last_seen_messages", 0):]
        for msg in new_msgs:
            if msg["sender"] != HUMAN_POWER:
                msg_tab = "GLOBAL" if msg["recipient"] == "GLOBAL" else msg["sender"]
                if msg_tab != current_tab:
                    st.toast(f"New message from {msg['sender']}!", icon="✉️")
        st.session_state.last_seen_messages = current_msg_count

    def format_tab(name):
        if unread_counts.get(name, 0) > 0:
            return f"🔴 {name} ({unread_counts[name]} new)"
        return name

    selected_chat = st.radio("Select Conversation", tab_names, format_func=format_tab, horizontal=True, label_visibility="collapsed", key="chat_tab_selector")

    chat_container = st.container(height=300)
    with chat_container:
        msgs = conversations.get(selected_chat, [])
        if not msgs:
            st.info(f"Start of conversation in {selected_chat}.")
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

    def submit_chat():
        st.session_state[f"submit_{selected_chat}"] = st.session_state[f"input_box_{selected_chat}"]
        st.session_state[f"input_box_{selected_chat}"] = ""

    user_input_placeholder = st.empty()
    user_input_placeholder.text_input("Message:", key=f"input_box_{selected_chat}", placeholder=f"Message {selected_chat}...", on_change=submit_chat)

    if f"submit_{selected_chat}" in st.session_state:
        user_input = st.session_state.pop(f"submit_{selected_chat}")
    else:
        user_input = None

    if st.button("Send Message", key=f"send_btn_{selected_chat}") or user_input:
        if user_input.strip():
            send_res = requests.post(
                f"{API_URL}/game/{st.session_state.game_id}/messages",
                json={
                    "sender": HUMAN_POWER,
                    "recipient": selected_chat,
                    "message": user_input,
                    "phase": current_phase
                },
                headers=get_headers()
            )
            if send_res.status_code == 200:
                st.toast("Message sent!", icon="✅")
                st.session_state.read_counts[selected_chat] = len(conversations[selected_chat]) + 1
                st.rerun() # Reruns just the fragment
            else:
                st.error("Failed to send message.")

# Call the fragment function. Conditionally disable polling if orders are submitted by removing run_every.
if not st.session_state.get('human_orders_submitted', False):
    render_chat()
else:
    # If we want it to stop polling, we can call the inner logic without the fragment decorator 
    # but Streamlit fragment's run_every handles this gracefully. 
    # Calling it directly is fine.
    render_chat()

# --- Game Over ---
if game_state["is_game_done"]:
    st.header("🏁 Game Over")
    winner = game_state["winner"]
    if winner:
        st.success(f"Winner: {', '.join(winner)}")
    else:
        st.info("Draw.")
