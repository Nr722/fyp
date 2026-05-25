import sys
import os
import pytest
from unittest.mock import patch, MagicMock
from diplomacy.engine.game import Game

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bot.bot import get_ai_bot_messages, finalize_ai_bot_orders
from bot.models import BotTurnResponse, BotOrderResponse, OrderItem, MessageItem

@patch('function_tools.db.get_connection')
@patch('bot.bot.invoke_with_retry')
def test_full_autonomous_cycle(mock_invoke, mock_get_conn):
    """
    Simulates a full autonomous cycle reading board state, 
    generating messages, executing orders and adjudicating.
    """
    game = Game()
    mock_conn = MagicMock()
    mock_get_conn.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchall.return_value = []
    
    # Provide LLM mock returns
    mock_invoke.side_effect = [
        # AI returns message during dialog phase
        BotTurnResponse(
            reasoning="Open negotiations.", 
            messages=[MessageItem(recipient="ENGLAND", message="Peace?")]
        ),
        # AI returns orders during finalization phase
        BotOrderResponse(
            reasoning="Standard opening.", 
            orders=[
                OrderItem(location="PAR", order="A PAR - BUR"),
                OrderItem(location="MAR", order="A MAR - SPA"),
                OrderItem(location="BRE", order="F BRE - PIC")
            ]
        )
    ]
    
    # Step 1: Messaging simulation
    messages = get_ai_bot_messages(game, "FRANCE", "test_e2e")
    assert len(messages) == 1
    assert messages[0]["recipient"] == "ENGLAND"
    
    # Step 2: Finalize orders simulation
    orders = finalize_ai_bot_orders(game, "FRANCE", "test_e2e")
    assert len(orders) == 3
    assert "A PAR - BUR" in orders
    
    # Step 3: Adjudication simulation
    game.set_orders("FRANCE", orders)
    game.process()
    
    # Verifying phase transitioned successfully after applying bot orders
    assert game.get_current_phase() == "F1901M"
