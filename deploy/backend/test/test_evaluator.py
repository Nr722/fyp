import sys
import os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bot.evaluator import evaluate_agreements
from diplomacy.engine.game import Game

@patch('bot.evaluator.ChatGoogleGenerativeAI')
@patch('function_tools.db.get_pending_agreements')
def test_evaluate_agreements_no_pending(mock_get_pending, mock_llm):
    """
    Test that the evaluator exits gracefully without calling the LLM 
    if there are no pending agreements.
    """
    mock_get_pending.return_value = []
    game = Game()
    evaluate_agreements("test_game", game)
    
    mock_llm.assert_not_called()

@patch('bot.evaluator.ChatGoogleGenerativeAI')
@patch('function_tools.db.update_agreement_status')
@patch('function_tools.db.get_pending_agreements')
def test_evaluate_agreements_success(mock_get_pending, mock_update, mock_llm):
    """
    Test that the evaluator correctly parses LLM response and updates the agreement status.
    """
    mock_get_pending.return_value = [
        {"id": 100, "bot_country": "ENGLAND", "agreed_with": "FRANCE", "agreement": "DMZ ENG"}
    ]
    game = Game()
    
    # Mocking orders
    game.set_orders("ENGLAND", ["F LON H"])
    
    # Setting up the LLM mock response
    mock_llm_instance = MagicMock()
    mock_llm.return_value = mock_llm_instance
    
    mock_response = MagicMock()
    mock_response.content = '''```json
    {
        "evaluations": [
            {
                "agreement_id": 100,
                "could_judge": true,
                "score": 100,
                "reasoning": "England held London, didn't move to ENG. DMZ respected."
            }
        ]
    }
    ```'''
    mock_llm_instance.invoke.return_value = mock_response

    evaluate_agreements("test_game", game)
    
    mock_update.assert_called_once_with(100, 100)
    mock_llm_instance.invoke.assert_called_once()
