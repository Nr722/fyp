import os
import sys
import json
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bot.evaluator import evaluate_agreements

class MockGame:
    def __init__(self, phase, orders_dict):
        self.phase = phase
        self.powers = list(orders_dict.keys())
        self._orders = orders_dict

    def get_orders(self, power):
        return self._orders.get(power, [])

    def get_current_phase(self):
        return self.phase

# --- The Golden Dataset ---
GOLDEN_DATASET = [
    {
        "name": "1. Clear DMZ Compliance",
        "phase": "S1901M",
        "agreements": [{"id": 1, "bot_country": "FRANCE", "agreed_with": "ENGLAND", "agreement": "DMZ the English Channel."}],
        "orders": {"ENGLAND": ["F LON - NTH"], "FRANCE": ["F BRE - MAO"]},
        "expected_could_judge": True,
        "expected_score_range": (80, 100)
    },
    {
        "name": "2. Clear DMZ Betrayal",
        "phase": "S1901M",
        "agreements": [{"id": 2, "bot_country": "FRANCE", "agreed_with": "ENGLAND", "agreement": "DMZ the English Channel."}],
        "orders": {"ENGLAND": ["F LON - ENG"], "FRANCE": ["F BRE - MAO"]},
        "expected_could_judge": True,
        "expected_score_range": (0, 20)
    },
    {
        "name": "3. Unjudgeable / Moving Closer",
        "phase": "S1901M",
        "agreements": [{"id": 3, "bot_country": "ITALY", "agreed_with": "AUSTRIA", "agreement": "Austria will attack Turkey."}],
        "orders": {"AUSTRIA": ["F TRI - ALB", "A BUD - SER"]},
        "expected_could_judge": False,
        "expected_score_range": None
    },
    {
        "name": "4. Support Compliance",
        "phase": "S1902M",
        "agreements": [{"id": 4, "bot_country": "FRANCE", "agreed_with": "GERMANY", "agreement": "Germany will support France into Belgium."}],
        "orders": {"FRANCE": ["A PIC - BEL"], "GERMANY": ["F HOL S A PIC - BEL"]},
        "expected_could_judge": True,
        "expected_score_range": (80, 100)
    },
    {
        "name": "5. Fake Support (Betrayal)",
        "phase": "S1902M",
        "agreements": [{"id": 5, "bot_country": "FRANCE", "agreed_with": "GERMANY", "agreement": "Germany will support France into Belgium."}],
        "orders": {"FRANCE": ["A PIC - BEL"], "GERMANY": ["F HOL - BEL"]}, 
        "expected_could_judge": True,
        "expected_score_range": (0, 20)
    },
    {
        "name": "6. Agreed Bounce Compliance",
        "phase": "S1901M",
        "agreements": [{"id": 6, "bot_country": "RUSSIA", "agreed_with": "TURKEY", "agreement": "Bounce in the Black Sea."}],
        "orders": {"RUSSIA": ["F SEV - BLA"], "TURKEY": ["F ANK - BLA"]},
        "expected_could_judge": True,
        "expected_score_range": (80, 100)
    },
    {
        "name": "7. Agreed Bounce Betrayal",
        "phase": "S1901M",
        "agreements": [{"id": 7, "bot_country": "TURKEY", "agreed_with": "RUSSIA", "agreement": "Bounce in the Black Sea."}],
        "orders": {"RUSSIA": ["F SEV H"], "TURKEY": ["F ANK - BLA"]},
        "expected_could_judge": True,
        "expected_score_range": (0, 20)
    },
{
        "name": "8. Ambiguous Posturing (Border Proximity)",
        "phase": "S1902M",
        "agreements": [{"id": 8, "bot_country": "GERMANY", "agreed_with": "RUSSIA", "agreement": "Stay out of the DMZ (Galicia)."}],
        # Germany moves to Silesia (borders Galicia but is not in it).
        "orders": {"GERMANY": ["A MUN - SIL"]}, 
        "expected_could_judge": False, # Should be 'could_judge=False' (not a betrayal yet)
        "expected_score_range": None
    },
    {
        "name": "9. Conditional Logic Failure",
        "phase": "S1902M",
        "agreements": [{"id": 9, "bot_country": "FRANCE", "agreed_with": "GERMANY", "agreement": "If Germany supports France to Belgium, France will support Germany to Holland."}],
        "orders": {"FRANCE": ["A PIC - BEL"], "GERMANY": ["A RUH - MUN"]}, # Germany betrayed the condition (didn't support)
        "expected_could_judge": True,
        "expected_score_range": (0, 20) 
    },
    {
        "name": "10. The 'False Help' Stab",
        "phase": "F1902M",
        "agreements": [{"id": 10, "bot_country": "ITALY", "agreed_with": "AUSTRIA", "agreement": "Italy will support Austria to Greece."}],
        # Italy attacks Greece instead of supporting
        "orders": {"ITALY": ["F ION - GRE"], "AUSTRIA": ["F ALB - GRE"]},
        "expected_could_judge": True,
        "expected_score_range": (0, 20)
    },
    {
        "name": "11. Implicit Stab (Fighting a Common Foe)",
        "phase": "F1903M",
        "agreements": [{"id": 11, "bot_country": "RUSSIA", "agreed_with": "GERMANY", "agreement": "Let's attack Austria together."}],
        # Russia attacks Austria, but ALSO moves a unit to attack Germany's unprotected center.
        "orders": {"RUSSIA": ["A GAL - VIE", "A WAR - SIL"]}, # SIL is a German center
        "expected_could_judge": True,
        "expected_score_range": (0, 20)
    },
    {
        "name": "12. Miscommunication/Ghosting",
        "phase": "S1901M",
        "agreements": [{"id": 12, "bot_country": "TURKEY", "agreed_with": "AUSTRIA", "agreement": "Bounce in the Black Sea."}],
        # Neither Turkey nor Russia issue a BLA order. They ignore each other.
        "orders": {"TURKEY": ["A CON H", "A SMY H"], "RUSSIA": ["F SEV H", "A WAR - GAL"]},
        "expected_could_judge": False, # Ghosting isn't a betrayal, it's just failure to coordinate.
        "expected_score_range": None
    }
]

# REMOVED the LLM patch. We want the real LLM to evaluate the prompt.
@patch('function_tools.db.update_agreement_status')
@patch('function_tools.db.add_agreement')
@patch('function_tools.db.get_pending_agreements')
@patch('function_tools.db.get_connection')
def run_evaluation_suite(mock_get_conn, mock_get_pending, mock_add_agreement, mock_update_status):
    
    mock_conn = MagicMock()
    mock_get_conn.return_value = mock_conn

    correct_predictions = 0
    total = len(GOLDEN_DATASET)

    print("=== Starting Golden Dataset Evaluation (LIVE LLM) ===\n")

    for scenario in GOLDEN_DATASET:
        print(f"Testing: {scenario['name']}")
        
        mock_game = MockGame(scenario['phase'], scenario['orders'])
        mock_get_pending.return_value = scenario['agreements']

        mock_update_status.reset_mock()

        # This will now hit the real Gemini API
        evaluate_agreements("test_game_123", mock_game)

        passed = False
        if not scenario['expected_could_judge']:
            if not mock_update_status.called:
                passed = True
            else:
                print("  [X] FAIL: Evaluator forced a judgment when it shouldn't have.")
        else:
            if mock_update_status.called:
                args, kwargs = mock_update_status.call_args
                assigned_score = args[1]
                min_score, max_score = scenario['expected_score_range']
                
                if min_score <= assigned_score <= max_score:
                    passed = True
                else:
                    print(f"  [X] FAIL: Expected score between {min_score}-{max_score}, got {assigned_score}")
            else:
                print("  [X] FAIL: Evaluator failed to make a judgment.")

        if passed:
            print("  [✓] PASS")
            correct_predictions += 1
        
        print("-" * 40)

    accuracy = (correct_predictions / total) * 100
    print(f"\n=== Final Accuracy: {correct_predictions}/{total} ({accuracy:.1f}%) ===")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    if not os.getenv("GEMINI_API_KEY"):
        print("WARNING: GEMINI_API_KEY not found in environment. The real API call will fail.")
    else:
        run_evaluation_suite()