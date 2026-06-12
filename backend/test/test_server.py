import sys
import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

# Add the backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from server import app, games, game_configs, get_current_user

# Override authentication dependency for testing
def mock_get_current_user():
    return "test_user"

app.dependency_overrides[get_current_user] = mock_get_current_user

# Initialize the test client
client = TestClient(app)

def test_create_game_endpoint():
    """
    Test that the /game/new endpoint successfully creates a game, 
    evaluates assignments, and updates the in-memory store.
    """
    response = client.post("/game/new", json={
        "human_power": "ENGLAND",
        "num_ai_bots": 2
    })
    
    # Assert successful HTTP request
    assert response.status_code == 200
    
    data = response.json()
    assert "game_id" in data
    assert data["human_power"] == "ENGLAND"
    
    # Ensure background defaults initialized securely
    game_id = data["game_id"]
    assert game_id in games
    assert "ENGLAND" not in data["ai_powers"]
    assert len(data["ai_powers"]) == 2

def test_get_possible_orders():
    """
    Ensure the possible orders lookup endpoint pulls accurate data
    from the instantiated diplomacy maps.
    """
    # Create game directly first
    response = client.post("/game/new", json={"human_power": "FRANCE"})
    data = response.json()
    game_id = data["game_id"]
    
    # Test getting orders for France
    response_orders = client.get(f"/game/{game_id}/orders/possible/FRANCE")
    assert response_orders.status_code == 200
    
    order_data = response_orders.json()
    assert "orderable_locations" in order_data
    # France normally starts with PAR, BRE, MAR
    assert "PAR" in order_data["orderable_locations"]
    assert "all_possible_orders" in order_data
    assert "power_units" in order_data

def test_get_game_state_404():
    """
    Test standard HTTP error throwing for an invalid/fake game ID
    """
    response = client.get("/game/fake-non-existent-id/state")
    assert response.status_code == 404
    assert response.json()["detail"] == "Game not found"

def test_submit_orders_endpoint():
    """
    Test submitting instructions formatting works. 
    We just test the pipeline wrapper, not necessarily the actual execution map.
    """
    response = client.post("/game/new", json={"human_power": "AUSTRIA"})
    data = response.json()
    game_id = data["game_id"]
    
    # Submit standard starting orders for Austria
    req_payload = {
        "power": "AUSTRIA",
        "orders": [
            "A VIE H",
            "A BUD - SER", 
            "F TRI - VEN"
        ]
    }
    
    response_submit = client.post(f"/game/{game_id}/orders", json=req_payload)
    assert response_submit.status_code == 200
    assert response_submit.json()["status"] == "success"

def test_rate_limit_fake_insert():
    """
    Verifies the debug endpoint handles queuing artificial events 
    used for testing UI modals properly.
    """
    response = client.post("/game/test-fake-game/test-rate-limit")
    assert response.status_code == 200
    
    response_get = client.get("/game/test-fake-game/rate-limits")
    assert response_get.status_code == 200
    assert len(response_get.json()["events"]) > 0
    assert response_get.json()["events"][-1]["bot_name"] == "TEST_BOT"

def test_get_game_state_success():
    """
    Test getting the game state (current phase, units, centers, etc.)
    """
    response = client.post("/game/new", json={"human_power": "ITALY"})
    data = response.json()
    game_id = data["game_id"]
    
    response_state = client.get(f"/game/{game_id}/state")
    assert response_state.status_code == 200
    
    state_data = response_state.json()
    assert "phase" in state_data
    assert "powers" in state_data
    assert "active_powers" in state_data
    assert "units" in state_data
    assert "centers" in state_data
    assert "map_svg" in state_data
    assert "is_game_done" in state_data
    assert len(state_data["powers"]) == 7  # 7 powers in Diplomacy

def test_clear_rate_limits():
    """
    Test the clear rate limits endpoint
    """
    # Add a fake event first
    client.post("/game/test-fake-game/test-rate-limit")
    
    # Verify event is there
    response_before = client.get("/game/test-fake-game/rate-limits")
    assert len(response_before.json()["events"]) > 0
    
    # Clear it
    response_clear = client.post("/game/test-fake-game/clear-rate-limits")
    assert response_clear.status_code == 200
    
    # Verify it's cleared
    response_after = client.get("/game/test-fake-game/rate-limits")
    assert len(response_after.json()["events"]) == 0

def test_get_messages():
    """
    Test retrieving messages for a power
    """
    response = client.post("/game/new", json={"human_power": "GERMANY"})
    data = response.json()
    game_id = data["game_id"]
    
    # Get messages for the human power
    response_msgs = client.get(f"/game/{game_id}/messages?power=GERMANY")
    assert response_msgs.status_code == 200
    
    msg_data = response_msgs.json()
    assert "messages" in msg_data
    assert isinstance(msg_data["messages"], list)

def test_send_message():
    """
    Test sending a message in the game
    """
    response = client.post("/game/new", json={"human_power": "SPAIN"})
    data = response.json()
    game_id = data["game_id"]
    
    # Send a message
    msg_payload = {
        "sender": "SPAIN",
        "recipient": "PORTUGAL",
        "message": "Let's form an alliance!",
        "phase": "S1901M"
    }
    
    response_send = client.post(f"/game/{game_id}/messages", json=msg_payload)
    assert response_send.status_code == 200

def test_process_turn():
    """
    Test processing a turn (advancing to next phase)
    """
    response = client.post("/game/new", json={"human_power": "RUSSIA"})
    data = response.json()
    game_id = data["game_id"]
    
    # Submit orders for the human power
    req_payload = {
        "power": "RUSSIA",
        "orders": [
            "A MOS H",
            "A WAR H",
            "F SEV H"
        ]
    }
    client.post(f"/game/{game_id}/orders", json=req_payload)
    
    # Process the turn
    process_payload = {
        "phase": "S1901M",
        "human_power": "RUSSIA"
    }
    
    response_process = client.post(f"/game/{game_id}/process", json=process_payload)
    assert response_process.status_code == 200
    
    process_data = response_process.json()
    assert "status" in process_data
    assert process_data["status"] == "success"
    assert "new_phase" in process_data
    assert "bot_orders" in process_data

def test_get_history_phase():
    """
    Test retrieving a specific historical phase map
    """
    response = client.post("/game/new", json={"human_power": "TURKEY"})
    data = response.json()
    game_id = data["game_id"]
    
    # Try to get history for S1901M (might fail if no history yet, which is ok)
    response_hist = client.get(f"/game/{game_id}/history/S1901M")
    # Can return 400 if phase doesn't exist yet, or 200 with SVG
    assert response_hist.status_code in [200, 400]
