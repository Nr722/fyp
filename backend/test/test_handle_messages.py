import sys
import os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bot.handle_messages import handle_incoming_message
from bot.models import BotReactionResponse, MessageItem, AgreementItem
from diplomacy.engine.game import Game

@patch('function_tools.db.get_connection')
@patch('bot.handle_messages.invoke_with_retry')
@patch('bot.handle_messages.add_agreement')
def test_handle_incoming_message_agreements(mock_add_agreement, mock_invoke, mock_get_conn):
    """
    Test handling a message, verifying LLM unpacks the response, sets messages, and saves agreements.
    """
    game = Game()
    
    # Mocking DB response for trust ledger
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchall.return_value = []
    mock_get_conn.return_value = mock_conn

    # Mock the returned Pydantic object
    mock_invoke.return_value = BotReactionResponse(
        reasoning="Agree to DMZ",
        messages=[
            MessageItem(recipient="ENGLAND", message="Sure, I agree to DMZ the channel.")
        ],
        agreements=[
            AgreementItem(agreed_with="ENGLAND", agreement="DMZ in the English Channel")
        ]
    )

    updated_orders, messages = handle_incoming_message(
        game=game,
        bot_name="FRANCE",
        sender="ENGLAND",
        message="Let's DMZ the english channel?",
        game_id="test_game",
        recipient="FRANCE"
    )

    assert len(messages) == 1
    assert messages[0]["recipient"] == "ENGLAND"
    assert messages[0]["message"] == "Sure, I agree to DMZ the channel."

    # Verify that add_agreement was called since an agreement was extracted
    mock_add_agreement.assert_called_once_with(
        game_id="test_game",
        bot_country="FRANCE",
        agreed_with="ENGLAND",
        agreement="DMZ in the English Channel",
        phase_made="S1901M"
    )
