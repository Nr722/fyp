import sys
import os
import pytest
from unittest.mock import patch, MagicMock

# Add the backend directory to sys.path to resolve imports cleanly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from function_tools.db import (
    init_db, save_message, get_game_messages,
    add_agreement, get_pending_agreements,
    update_agreement_status, get_trust_history
)

@patch('function_tools.db.get_connection')
def test_init_db(mock_get_conn):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_get_conn.return_value = mock_conn

    init_db()

    assert mock_cursor.execute.call_count == 2
    mock_conn.commit.assert_called_once()
    mock_conn.close.assert_called_once()

@patch('function_tools.db.get_connection')
def test_save_message(mock_get_conn):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_get_conn.return_value = mock_conn

    save_message("game1", "FRANCE", "ENGLAND", "Let's ally", "S1901M")
    
    mock_cursor.execute.assert_called_once()
    sql, params = mock_cursor.execute.call_args[0]
    assert "INSERT INTO game_messages" in sql
    assert params == ("game1", "FRANCE", "ENGLAND", "Let's ally", "S1901M")
    mock_conn.commit.assert_called_once()

@patch('function_tools.db.get_connection')
def test_get_game_messages(mock_get_conn):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_get_conn.return_value = mock_conn
    mock_cursor.fetchall.return_value = [{"sender": "FRANCE", "message": "Hi"}]

    result = get_game_messages("game1")
    
    mock_cursor.execute.assert_called_once()
    sql, params = mock_cursor.execute.call_args[0]
    assert "SELECT sender, recipient, message" in sql
    assert params == ("game1",)
    assert result == [{"sender": "FRANCE", "message": "Hi"}]

@patch('function_tools.db.get_connection')
def test_add_agreement(mock_get_conn):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_get_conn.return_value = mock_conn

    add_agreement("game1", "FRANCE", "ENGLAND", "DMZ in ENG", "S1901M")
    
    mock_cursor.execute.assert_called_once()
    sql, params = mock_cursor.execute.call_args[0]
    assert "INSERT INTO trust_ledger" in sql
    assert params == ("game1", "FRANCE", "ENGLAND", "DMZ in ENG", "S1901M")

@patch('function_tools.db.get_connection')
def test_get_pending_agreements(mock_get_conn):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_get_conn.return_value = mock_conn
    mock_cursor.fetchall.return_value = [{"id": 1, "agreement": "DMZ"}]

    result = get_pending_agreements("game1")
    
    mock_cursor.execute.assert_called_once()
    sql, params = mock_cursor.execute.call_args[0]
    assert "followed IS NULL" in sql
    assert params == ("game1",)
    assert result == [{"id": 1, "agreement": "DMZ"}]

@patch('function_tools.db.get_connection')
def test_update_agreement_status(mock_get_conn):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_get_conn.return_value = mock_conn

    update_agreement_status(1, 100)
    
    mock_cursor.execute.assert_called_once()
    sql, params = mock_cursor.execute.call_args[0]
    assert "UPDATE trust_ledger" in sql
    assert params == (100, 1) # (followed, agreement_id)
