import sys
import os
import pytest
from fastapi.testclient import TestClient

# Add the backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from server import app, games, game_configs

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
