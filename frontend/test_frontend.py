import os
import pytest
from unittest.mock import patch, MagicMock

# The Streamlit testing framework allows us to spin up a headless version of the UI
from streamlit.testing.v1 import AppTest

@patch('frontend.requests.get')
@patch('frontend.requests.post')
def test_frontend_login_and_game_init(mock_post, mock_get):
    """
    Test the Streamlit UI loading and handling login,
    preventing actual HTTP calls to the backend via mocks.
    """
    # 1. Mock the API responses the frontend expects from the backend
    mock_post.return_value = MagicMock(
        status_code=200, 
        json=lambda: {
            "game_id": "test_game_123",
            "human_power": "FRANCE",
            "ai_powers": ["ENGLAND", "GERMANY"]
        }
    )
    
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "phase": "S1901M",
            "powers": ["FRANCE", "ENGLAND", "GERMANY"],
            "active_powers": ["FRANCE", "ENGLAND", "GERMANY"],
            "units": {},
            "centers": {},
            "is_game_done": False,
            "winner": None,
            "map_svg": "<svg>MockMap</svg>",
            "history_svg": None,
            "past_phases": []
        }
    )

    # 2. Inject environment variables for the login test
    with patch.dict('os.environ', {'APP_USERNAME': 'admin', 'APP_PASSWORD': 'password'}):
        # 3. Launch the headless Streamlit App
        at = AppTest.from_file("frontend.py").run()
        
        # 4. Verify we hit the Login barrier first
        assert at.title[0].value == "Diplomacy Login"
        
        # 5. Simulate human logging in
        at.text_input[0].input("admin")
        at.text_input[1].input("password")
        at.button[0].click().run() # Click login
        
        # 6. Verify we passed the login and accessed the main Game UI
        assert at.title[0].value == " Diplomacy Game"
        
        # Verify the backend endpoints were actually called by the UI to fetch data
        mock_post.assert_called_once()
        assert "/game/new" in mock_post.call_args[0][0]
        
        # Verify the UI successfully extracted and used the mock data
        assert at.sidebar.header[0].value == "Game Controls"
