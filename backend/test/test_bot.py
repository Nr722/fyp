import sys
import os
import pytest
from unittest.mock import patch, MagicMock

# Add the backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bot.bot import (
    _get_common_context,
    get_ai_bot_messages,
    finalize_ai_bot_orders,
    invoke_with_retry
)
from bot.models import BotTurnResponse, BotOrderResponse, OrderItem, MessageItem
from diplomacy.engine.game import Game

@patch('function_tools.db.get_connection')
def test_get_common_context(mock_get_conn):
    """
    Tests the context builder to ensure it correctly shapes the prompt given standard Game objects
    and doesn't crash on DB absence.
    """
    game = Game()
    # Mocking DB response for trust ledger
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchall.return_value = [("ENGLAND", "DMZ ENG", 1, "S1901M")]
    mock_get_conn.return_value = mock_conn

    phase, board_state, prev_turn, trust_history, tactical = _get_common_context(
        game, "FRANCE", "test_game_1", include_tactical=True
    )
    
    assert phase == "S1901M"
    assert "CURRENT BOARD STATE" in board_state
    assert "FRANCE:" in board_state
    assert "ENGLAND FOLLOWED agreement" in trust_history
    assert "TACTICAL ANALYSIS" in tactical

@patch('bot.bot.invoke_with_retry')
def test_get_ai_bot_messages(mock_invoke):
    """
    Test message strategy isolation, ensuring LLM output structs are properly unpacked.
    """
    game = Game()
    
    # Mock the returned Pydantic object
    mock_invoke.return_value = BotTurnResponse(
        reasoning="I want an alliance with England.",
        messages=[
            MessageItem(recipient="ENGLAND", message="hey want to dmz channel?")
        ]
    )
    
    messages = get_ai_bot_messages(game, "FRANCE", "test_game_1")
    
    assert len(messages) == 1
    assert messages[0]["recipient"] == "ENGLAND"
    assert messages[0]["message"] == "hey want to dmz channel?"
    mock_invoke.assert_called_once()

@patch('bot.bot.invoke_with_retry')
def test_finalize_ai_bot_orders_success(mock_invoke):
    """
    Tests that a valid structural return from the LLM correctly parses into Game.set_orders format.
    """
    game = Game()
    
    # France default is A PAR, A MAR, F BRE (Standard standard map S1901M)
    mock_invoke.return_value = BotOrderResponse(
        reasoning="Standard open",
        orders=[
            OrderItem(location="PAR", order="A PAR - BUR"),
            OrderItem(location="MAR", order="A MAR H"),
            OrderItem(location="BRE", order="F BRE - PIC")
        ]
    )
    
    orders = finalize_ai_bot_orders(game, "FRANCE", "test_game_1")
    
    assert len(orders) == 3
    assert "A PAR - BUR" in orders
    assert "A MAR H" in orders
    assert "F BRE - PIC" in orders
    
def test_invoke_with_retry_logic():
    """
    Test the rate limit exponential backoff handler.
    """
    mock_model = MagicMock()
    
    # Throw a 429 quota error the first time, then succeed the second time
    mock_model.invoke.side_effect = [
        Exception("429 resource_exhausted, retry in 0.1s"), 
        "Success"
    ]
    
    result = invoke_with_retry(mock_model, [], max_retries=3, initial_delay=0.1)
    
    assert result == "Success"
    assert mock_model.invoke.call_count == 2
