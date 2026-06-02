import os
import inspect
import sys
import time
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Importing the actual subroutines to profile
from bot.evaluator import evaluate_agreements
import bot.evaluator as evaluator_module
from bot.bot import get_bot_messages, finalize_ai_bot_orders
from bot.handle_messages import handle_incoming_message
import bot.bot as bot_module
import bot.handle_messages as handle_messages_module
import function_tools.tactical_scorer as tactical_scorer_module

from langchain_core.callbacks import BaseCallbackHandler

class TokenTrackerCallback(BaseCallbackHandler):
    """Intercepts the raw LLM output before Pydantic parsing strips the metadata."""
    def __init__(self):
        self.out_tokens = 0

    def on_llm_end(self, response, **kwargs):
        try:
            # Grab the raw message from the generation payload
            msg = response.generations[0][0].message
            if hasattr(msg, 'usage_metadata') and msg.usage_metadata:
                self.out_tokens = msg.usage_metadata.get('output_tokens', 0)
        except Exception:
            pass

class MockMap:
    def __init__(self):
        self.scs = [
            "LON", "EDI", "LVP", "PAR", "BRE", "MAR", "BUR", "PIC", "BEL", "HOL",
            "BER", "KIE", "MUN", "RUH", "ROM", "VEN", "NAP", "VIE", "BUD", "TRI",
            "MOS", "STP", "SEV", "WAR", "ANK", "CON", "SMY", "GRE", "SER", "BUL",
            "GAL", "SIL", "BLA", "ENG"
        ]

    def abut_list(self, loc):
        adjacency = {
            "LON": ["ENG", "NTH", "BEL"],
            "EDI": ["NTH", "NWG"],
            "LVP": ["IRI", "WAL", "YOR"],
            "PAR": ["BUR", "PIC", "GAS"],
            "BRE": ["PIC", "ENG", "MAO", "GAS"],
            "MAR": ["BUR", "GAS", "PIE"],
            "BUR": ["PAR", "MAR", "BEL", "RUH", "MUN", "PIC"],
            "PIC": ["PAR", "BRE", "BEL", "ENG", "BUR"],
            "BEL": ["PIC", "BUR", "HOL", "RUH", "ENG"],
            "HOL": ["BEL", "RUH", "KIE", "ENG", "NTH"],
            "BER": ["KIE", "MUN", "PRU", "BAL"],
            "KIE": ["HOL", "BER", "MUN", "BAL", "DEN"],
            "MUN": ["RUH", "BUR", "KIE", "BER", "SIL", "BOH"],
            "RUH": ["HOL", "BEL", "BUR", "MUN", "KIE"],
            "VIE": ["BOH", "GAL", "BUD", "TRI", "TYR"],
            "BUD": ["VIE", "GAL", "SER", "TRI", "RUM"],
            "TRI": ["VIE", "BUD", "SER", "ALB", "ADR"],
            "GAL": ["VIE", "BUD", "WAR", "UKR", "SIL"],
            "SIL": ["MUN", "BER", "WAR", "GAL", "BOH"],
            "ANK": ["CON", "SMY", "BLA"],
            "CON": ["ANK", "SMY", "BLA", "BUL"],
            "SMY": ["ANK", "CON", "BUL", "AEG"],
            "BLA": ["ANK", "CON", "SEV", "RUM"],
            "SEV": ["BLA", "RUM", "UKR", "ARM"],
            "GRE": ["ALB", "BUL", "ION", "AEG"],
            "SER": ["BUD", "TRI", "BUL", "GRE", "RUM"],
            "BUL": ["CON", "GRE", "SER", "RUM", "AEG"],
        }
        return adjacency.get(loc, [])


class ProfiledInvokeTracker:
    def __init__(self):
        self.structured_calls = 0
        self.first_pass_successes = 0
        self.retry_loop_triggers = 0
        self.call_latencies = []

    @staticmethod
    def _is_retryable_error(err_msg):
        return any(token in err_msg for token in ("429", "rate limit", "quota", "resource_exhausted"))

    def __call__(self, model, history, max_retries=1, initial_delay=5, bot_name="Bot"):
        self.structured_calls += 1
        telemetry["structured_output_calls"] += 1
        for attempt in range(max_retries):
            try:
                if attempt == 0:
                    _record_prompt_tokens(history)
                
                start = time.perf_counter()
                
                # --- NEW INTERCEPTOR LOGIC ---
                token_tracker = TokenTrackerCallback()
                
                # Pass the tracker into the config so it can catch the raw message
                result = model.invoke(history, config={"callbacks": [token_tracker]})
                
                elapsed = time.perf_counter() - start
                
                # Extract the saved tokens from the tracker, not the result object
                out_tokens = token_tracker.out_tokens
                if out_tokens > 0:
                    telemetry["completion_prompt_tokens"].append(out_tokens)
                else:
                    # Absolute fallback if callback misses it
                    fallback = int(len(str(result).split()) * 1.3)
                    telemetry["completion_prompt_tokens"].append(fallback)
                
                # --- RESTORED BLOCK ---
                if attempt == 0:
                    self.first_pass_successes += 1
                    telemetry["first_pass_structural_successes"] += 1
                    self.call_latencies.append(elapsed)
                    telemetry["llm_inference_latencies"].append(elapsed)
                # ----------------------
                
                return result
            except Exception as exc:
                err_msg = str(exc).lower()
                
                # Check if it was a structural/parsing error
                if "validation" in err_msg or "json" in err_msg or "pydantic" in err_msg:
                    if attempt == 0:
                        telemetry["structural_failures"] += 1
                else:
                    if attempt == 0:
                        telemetry["service_failures"] += 1

                if self._is_retryable_error(err_msg) and attempt < max_retries - 1:
                    if attempt == 0:
                        self.retry_loop_triggers += 1
                        telemetry["retry_loop_triggers"] += 1
                    delay = initial_delay * (2 ** attempt)
                    time.sleep(delay)
                    continue
                raise


profiled_invoke_with_retry = ProfiledInvokeTracker()


class ProfiledTacticalScorer:
    def __init__(self):
        self.latencies = []

    def __call__(self, game, power):
        start = time.perf_counter()
        result = tactical_scorer_module.score_individual_orders(game, power)
        elapsed = time.perf_counter() - start
        self.latencies.append(elapsed)
        telemetry["tactical_scorer_latencies"].append(elapsed)
        return result


profiled_score_individual_orders = ProfiledTacticalScorer()


bot_module.invoke_with_retry = profiled_invoke_with_retry
handle_messages_module.invoke_with_retry = profiled_invoke_with_retry
evaluator_module.invoke_with_retry = profiled_invoke_with_retry
bot_module.score_individual_orders = profiled_score_individual_orders
handle_messages_module.score_individual_orders = profiled_score_individual_orders

class MockGame:
    def __init__(self, phase, scenario):
        self.phase = phase
        self.powers = list(scenario["orders"].keys())
        self._orders = scenario["orders"]
        self._units = scenario["units"]
        self._centers = scenario["centers"]
        self._orderable_locations = scenario["orderable_locations"]
        self._possible_orders = scenario["possible_orders"]
        self.map = MockMap()

    def get_orders(self, power):
        return self._orders.get(power, [])

    def get_current_phase(self):
        return self.phase

    def get_phase_history(self) -> list:
        return []

    def get_all_possible_orders(self) -> dict:
        return self._possible_orders

    def get_orderable_locations(self, power) -> list:
        return self._orderable_locations.get(power, [])

    def get_units(self, power=None):
        if power is None:
            return self._units
        return self._units.get(power, [])

    def get_centers(self, power=None):
        if power is None:
            return self._centers
        return self._centers.get(power, [])

    def get_state(self) -> dict:
        return {
            "name": self.phase.name if hasattr(self.phase, "name") else str(self.phase),
            "units": self._units,
            "centers": self._centers,
            "homes": {p: [] for p in self.powers},
            "influence": {p: [] for p in self.powers},
            "civilian": {p: [] for p in self.powers},
            "builder": {p: [] for p in self.powers}
        }
    
PROFILING_SUITE = [
    {
        "name": "Test 1: Standard DMZ Evaluation",
        "phase": "S1901M",
        "use_tactical": False,
        "units": {
            "ENGLAND": ["F LON", "A EDI"],
            "FRANCE": ["F BRE", "A PAR"],
            "GERMANY": ["A MUN"]
        },
        "centers": {
            "ENGLAND": ["LON", "EDI"],
            "FRANCE": ["PAR", "BRE"],
            "GERMANY": ["MUN"]
        },
        "orderable_locations": {
            "ENGLAND": ["LON", "EDI"],
            "FRANCE": ["BRE", "PAR"]
        },
        "possible_orders": {
            "LON": ["F LON - NTH", "F LON - ENG", "F LON H"],
            "EDI": ["A EDI - LVP", "A EDI H"],
            "BRE": ["F BRE - MAO", "F BRE - ENG", "F BRE H"],
            "PAR": ["A PAR - BUR", "A PAR H"]
        },
        "agreements": [{"id": 1, "bot_country": "FRANCE", "agreed_with": "ENGLAND", "agreement": "DMZ the English Channel."}],
        "orders": {"ENGLAND": ["F LON - NTH"], "FRANCE": ["F BRE - MAO"]},
        "sender": "ENGLAND", "recipient": "FRANCE", "message": "DMZ the English Channel."
    },
    {
        "name": "Test 2: Tactical Scorer Active (Support Execution)",
        "phase": "S1902M",
        "use_tactical": True, 
        "units": {
            "GERMANY": ["F HOL", "A MUN"],
            "FRANCE": ["A PIC", "F BEL"]
        },
        "centers": {
            "GERMANY": ["HOL", "MUN"],
            "FRANCE": ["PIC", "BEL"]
        },
        "orderable_locations": {
            "GERMANY": ["HOL"],
            "FRANCE": ["PIC"]
        },
        "possible_orders": {
            "HOL": ["F HOL S A PIC - BEL", "F HOL - BEL", "F HOL H"],
            "PIC": ["A PIC - BEL", "A PIC H"]
        },
        "agreements": [{"id": 4, "bot_country": "FRANCE", "agreed_with": "GERMANY", "agreement": "Germany will support France into Belgium."}],
        "orders": {"FRANCE": ["A PIC - BEL"], "GERMANY": ["F HOL S A PIC - BEL"]},
        "sender": "GERMANY", "recipient": "FRANCE", "message": "Supporting you to Belgium."
    },
    {
        "name": "Test 3: Complex Fake Support Betrayal Parsing",
        "phase": "S1902M",
        "use_tactical": True,
        "units": {
            "GERMANY": ["F HOL", "A MUN"],
            "FRANCE": ["A PIC", "F BEL"]
        },
        "centers": {
            "GERMANY": ["HOL", "MUN"],
            "FRANCE": ["PIC", "BEL"]
        },
        "orderable_locations": {
            "GERMANY": ["HOL"],
            "FRANCE": ["PIC"]
        },
        "possible_orders": {
            "HOL": ["F HOL - BEL", "F HOL H"],
            "PIC": ["A PIC - BEL", "A PIC H"]
        },
        "agreements": [{"id": 5, "bot_country": "FRANCE", "agreed_with": "GERMANY", "agreement": "Germany will support France into Belgium."}],
        "orders": {"FRANCE": ["A PIC - BEL"], "GERMANY": ["F HOL - BEL"]},
        "sender": "GERMANY", "recipient": "FRANCE", "message": "I will support you."
    },
    {
        "name": "Test 4: High Density Tactical Graph (Implicit Stab)",
        "phase": "F1903M",
        "use_tactical": True,
        "units": {
            "RUSSIA": ["A GAL", "A WAR"],
            "GERMANY": ["A MUN"]
        },
        "centers": {
            "RUSSIA": ["WAR", "GAL"],
            "GERMANY": ["MUN"]
        },
        "orderable_locations": {
            "RUSSIA": ["GAL", "WAR"],
            "GERMANY": ["MUN"]
        },
        "possible_orders": {
            "GAL": ["A GAL - VIE", "A GAL - SIL", "A GAL H"],
            "WAR": ["A WAR - SIL", "A WAR H"],
            "MUN": ["A MUN H"]
        },
        "agreements": [{"id": 11, "bot_country": "RUSSIA", "agreed_with": "GERMANY", "agreement": "Let's attack Austria together."}],
        "orders": {"RUSSIA": ["A GAL - VIE", "A WAR - SIL"], "GERMANY": ["A MUN H"]},
        "sender": "RUSSIA", "recipient": "GERMANY", "message": "Attacking Austria now."
    },
    {
        "name": "Test 5: Passive State Evaluation (Ghosting)",
        "phase": "S1901M",
        "use_tactical": False,
        "units": {
            "TURKEY": ["A CON", "F ANK"],
            "RUSSIA": ["F SEV"]
        },
        "centers": {
            "TURKEY": ["CON", "ANK"],
            "RUSSIA": ["SEV"]
        },
        "orderable_locations": {
            "TURKEY": ["CON", "ANK"],
            "RUSSIA": ["SEV"]
        },
        "possible_orders": {
            "CON": ["A CON H", "A CON - BUL"],
            "ANK": ["F ANK - BLA", "F ANK H"],
            "SEV": ["F SEV H", "F SEV - BLA"]
        },
        "agreements": [{"id": 12, "bot_country": "TURKEY", "agreed_with": "AUSTRIA", "agreement": "Bounce in the Black Sea."}],
        "orders": {"TURKEY": ["A CON H"], "RUSSIA": ["F SEV H"]},
        "sender": "TURKEY", "recipient": "RUSSIA", "message": "Let's bounce."
    }
]

# Track metrics cleanly
telemetry = {
    "tactical_scorer_latencies": [],
    "llm_inference_latencies": [],
    "context_assembly_latencies": [],
    "inbound_reply_latencies": [],
    "order_finalization_latencies": [],
    "trust_evaluator_latencies": [],
    "structured_output_calls": 0,
    "first_pass_structural_successes": 0,
    "structural_failures": 0,
    "service_failures": 0,
    "retry_loop_triggers": 0,
    "message_prompt_tokens": [],
    "reply_prompt_tokens": [],
    "order_prompt_tokens": [],
    "trust_evaluator_tokens": [],
    "completion_prompt_tokens": [], 
}


def _make_mock_game(run):
    return MockGame(run['phase'], run)


def _build_ai_metrics_message():
    total_calls = telemetry["structured_output_calls"]
    first_pass = telemetry["first_pass_structural_successes"]
    retry_triggers = telemetry["retry_loop_triggers"]
    first_pass_rate = (first_pass / total_calls) * 100 if total_calls else 100.0
    retry_rate = (retry_triggers / total_calls) * 100 if total_calls else 0.0
    return total_calls, first_pass, retry_triggers, first_pass_rate, retry_rate


def _token_count_for_history(history):
    try:
        token_model = bot_module.get_model()
        return token_model.get_num_tokens_from_messages(history)
    except Exception:
        return sum(max(1, len(str(message.content).split())) for message in history)


def _record_prompt_tokens(history):
    frame = inspect.currentframe()
    caller = frame.f_back.f_back.f_code.co_name if frame and frame.f_back and frame.f_back.f_back else "unknown"
    token_count = _token_count_for_history(history)
    if caller == "get_ai_bot_messages":
        telemetry["message_prompt_tokens"].append(token_count)
    elif caller == "handle_incoming_message":
        telemetry["reply_prompt_tokens"].append(token_count)
    elif caller == "finalize_ai_bot_orders":
        telemetry["order_prompt_tokens"].append(token_count)
    elif caller == "evaluate_agreements":
        telemetry["trust_evaluator_tokens"].append(token_count)

@patch('function_tools.db.update_agreement_status')
@patch('function_tools.db.add_agreement')
@patch('function_tools.db.get_pending_agreements')
@patch('function_tools.db.get_connection')
def run_benchmarks(mock_get_conn, mock_get_pending, mock_add_agreement, mock_update_status):
    mock_conn = MagicMock()
    mock_get_conn.return_value = mock_conn

    print("=== Starting Isolated 5-Stage System Profiling Run ===\n")
    
    for run in PROFILING_SUITE:
        print(f"Running Subroutine Profiling: {run['name']}")
        mock_game = _make_mock_game(run)
        mock_get_pending.return_value = run['agreements']
        
        # 1. Profile Outbound Message Generation (Row 5 Tokens)
        # T_total = t_heuristic + t_context + t_inference
        t_start = time.perf_counter()
        profiled_score_individual_orders.latencies = []
        profiled_invoke_with_retry.call_latencies = []
        
        _ = get_bot_messages(mock_game, run['sender'], bot_type="ai", game_id="prof_123", use_tactical=run['use_tactical'])
        t_total = time.perf_counter() - t_start
        
        t_heur = sum(profiled_score_individual_orders.latencies)
        t_inf = sum(profiled_invoke_with_retry.call_latencies)
        t_ctx = max(0, t_total - t_heur - t_inf)
        telemetry["context_assembly_latencies"].append(t_ctx)

        # 2. Profile Message Inbound & Reply Handlers (Row 2 Latency + Tokens)
        r_start = time.perf_counter()
        profiled_score_individual_orders.latencies = []
        profiled_invoke_with_retry.call_latencies = []
        
        _, _ = handle_incoming_message(
            game=mock_game, bot_name=run['recipient'], sender=run['sender'], 
            message=run['message'], game_id="prof_123", recipient=run['recipient'], 
            use_tactical=run['use_tactical']
        )
        r_total = time.perf_counter() - r_start
        r_heur = sum(profiled_score_individual_orders.latencies)
        r_inf = sum(profiled_invoke_with_retry.call_latencies)
        r_ctx = max(0, r_total - r_heur - r_inf)
        telemetry["context_assembly_latencies"].append(r_ctx)
        telemetry["inbound_reply_latencies"].append(r_total)

        # 3. Profile Order Finalization Passes (Row 3 Latency + Tokens)
        f_start = time.perf_counter()
        profiled_score_individual_orders.latencies = []
        profiled_invoke_with_retry.call_latencies = []
        
        # NOTE: finalize_ai_bot_orders might make multiple LLM calls if there are many units, 
        # so t_total is the aggregate for the whole "Pass".
        _ = finalize_ai_bot_orders(mock_game, run['sender'], game_id="prof_123", use_tactical=run['use_tactical'])
        f_total = time.perf_counter() - f_start
        f_heur = sum(profiled_score_individual_orders.latencies)
        f_inf = sum(profiled_invoke_with_retry.call_latencies)
        f_ctx = max(0, f_total - f_heur - f_inf)
        telemetry["context_assembly_latencies"].append(f_ctx)
        telemetry["order_finalization_latencies"].append(f_total)

        # 4. Profile Trust Ledger Evaluator (Row 4 Latency)
        e_start = time.perf_counter()
        evaluate_agreements("prof_123", mock_game)
        telemetry["trust_evaluator_latencies"].append(time.perf_counter() - e_start)
        
        print("Stage complete.\n" + "-"*40)

    print_final_telemetry()

def print_final_telemetry():
    print("\n" + "="*80)
    print("                COMPUTATIONAL EFFICIENCY PROFILE (LATEX COMPATIBLE)")
    print("="*80)
    
    def log_full_row(label, latencies, tokens=None, is_output_tokens=False):
        mean_lat = sum(latencies)/len(latencies) if latencies else 0
        max_lat = max(latencies) if latencies else 0
        mean_tok = sum(tokens)/len(tokens) if tokens else 0
        samples = len(latencies) if latencies else (len(tokens) if tokens else 0)
        
        tok_type = "Out Tokens:" if is_output_tokens else "In Tokens: "
        tok_str = f"{mean_tok:6.1f}" if tokens else "  --  "
        lat_str = f"Mean: {mean_lat:6.4f}s | Max: {max_lat:6.4f}s" if latencies else "        --            "
        
        print(f"{label:<32} {lat_str} | {tok_type} {tok_str} | n={samples}")

    log_full_row("Tactical Scorer Matrix", telemetry["tactical_scorer_latencies"])
    log_full_row("Inbound Message Reply", telemetry["inbound_reply_latencies"], telemetry["reply_prompt_tokens"])
    log_full_row("Order Finalization Pass", telemetry["order_finalization_latencies"], telemetry["order_prompt_tokens"])
    log_full_row("Trust Ledger Evaluator Module", telemetry["trust_evaluator_latencies"], telemetry["trust_evaluator_tokens"])
    log_full_row("Message Generation Prompt", [], telemetry["message_prompt_tokens"])
    log_full_row("Message Generation Completion", [], telemetry["completion_prompt_tokens"], is_output_tokens=True)

    print("\n" + "-"*80)
    print("SUB-ROUTINE BREAKDOWN (for Equation: T = t_context + t_inference + t_heuristic)")
    print("-"*80)
    
    def log_metric(label, data_list):
        if data_list:
            avg = sum(data_list) / len(data_list)
            print(f"{label:<32} Mean: {avg:6.4f}s | Max: {max(data_list):6.4f}s (n={len(data_list)})")
        else:
            print(f"{label:<32} No samples recorded.")

    log_metric("Context Assembly (t_context):", telemetry["context_assembly_latencies"])
    log_metric("LLM Inf + Parse (t_inference):", telemetry["llm_inference_latencies"])
    log_metric("Tactical Scorer (t_heuristic):", telemetry["tactical_scorer_latencies"])

    total_calls = telemetry["structured_output_calls"]
    first_pass = telemetry["first_pass_structural_successes"]
    struct_fails = telemetry["structural_failures"]
    service_fails = telemetry["service_failures"]
    retry_triggers = telemetry["retry_loop_triggers"]
    
    first_pass_rate = (first_pass / total_calls) * 100 if total_calls else 100.0
    
    print("\nLLM Structural Reliability:")
    print(f"- Structured-output calls observed: {total_calls}")
    print(f"- First-pass Successes:           {first_pass}")
    print(f"- First-pass Structural Failures: {struct_fails} (Bad JSON/Scheme)")
    print(f"- First-pass Service Failures:    {service_fails} (404/500/Network)")
    print(f"- Retry-loop triggers:           {retry_triggers}")
    print(f"- Reliability Adjusted Rate:      {first_pass_rate:.2f}%")
    print("="*80)

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    run_benchmarks()