import os
import inspect
import sys
import time
from collections import defaultdict
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from langchain_core.callbacks import BaseCallbackHandler

from bot.evaluator import evaluate_agreements
import bot.evaluator as evaluator_module
from bot.bot import get_bot_messages, finalize_ai_bot_orders
from bot.handle_messages import handle_incoming_message
import bot.bot as bot_module
import bot.handle_messages as handle_messages_module
import function_tools.tactical_scorer as tactical_scorer_module

PRICING = {
    "gemini-3.1-flash-lite": {"input": 0.075, "cached_input": 0.01875, "output": 0.30},
    "gemma-12b":             {"input": 0.15,  "cached_input": 0.15,    "output": 0.15}, 
    "unknown":               {"input": 0.0,   "cached_input": 0.0,     "output": 0.0}
}

def call_cost(model_name, inp, cached, out):
    p = PRICING.get(model_name, PRICING["unknown"])
    full_price_in = max(0, inp - cached)
    return (full_price_in * p["input"] + cached * p["cached_input"] + out * p["output"]) / 1_000_000

class UsageTrackerCallback(BaseCallbackHandler):
    def __init__(self):
        self.input_tokens = self.output_tokens = self.cached_tokens = self.reasoning_tokens = self.total_tokens = 0
        self._estimated_in = 0

    def on_llm_start(self, serialized, prompts, **kwargs):
        self._estimated_in = sum(int(len(str(p).split()) * 1.3) for p in prompts)

    def on_llm_end(self, response, **kwargs):
        try:
            msg = response.generations[0][0].message
            um = getattr(msg, "usage_metadata", None) or {}

            self.input_tokens  = um.get("input_tokens", 0)
            self.output_tokens = um.get("output_tokens", 0)

            if self.input_tokens == 0:
                self.input_tokens = self._estimated_in
                self.output_tokens = int(len(str(msg.content).split()) * 1.3)

            self.total_tokens = self.input_tokens + self.output_tokens
            
            in_d  = um.get("input_token_details", {})  or {}
            out_d = um.get("output_token_details", {}) or {}
            self.cached_tokens    = in_d.get("cache_read", 0)
            self.reasoning_tokens = out_d.get("reasoning", 0)
        except Exception:
            pass

def _current_caller():
    frame = inspect.currentframe()
    target_tasks = {
        "get_bot_messages": "Outbound Message",
        "handle_incoming_message": "Inbound Reply",
        "finalize_ai_bot_orders": "Order Finalize",
        "evaluate_agreements": "Trust Evaluator"
    }
    while frame:
        name = frame.f_code.co_name
        if name in target_tasks: return target_tasks[name]
        frame = frame.f_back
    return "Unknown Task"

telemetry = {
    "tactical_scorer_latencies": [],
    "llm_inference_latencies": [],
    "structured_output_calls": 0,
    "first_pass_structural_successes": 0,
    "structural_failures": 0,
    "service_failures": 0,
    "retry_loop_triggers": 0,
    "usage": []
}

class ProfiledInvokeTracker:
    @staticmethod
    def _is_retryable_error(err_msg):
        return any(token in err_msg for token in ("429", "rate limit", "quota", "resource_exhausted"))

    def __call__(self, model, history, max_retries=1, initial_delay=5, bot_name="Bot"):
        telemetry["structured_output_calls"] += 1
        
        for attempt in range(max_retries):
            try:
                start = time.perf_counter()
                tracker = UsageTrackerCallback()
                
                result = model.invoke(history, config={"callbacks": [tracker]})
                elapsed = time.perf_counter() - start
                
                # Unwrap if necessary (with_structured_output wraps the base model)
                base_model = getattr(model, "bound", model)
                raw_model = str(getattr(base_model, "model_name", getattr(base_model, "model", "unknown"))).lower()
                pricing_key = "gemma-12b" if "gemma" in raw_model else "gemini-3.1-flash-lite"
                
                telemetry["usage"].append({
                    "task": _current_caller(),
                    "model": pricing_key,
                    "in": tracker.input_tokens,
                    "cached": tracker.cached_tokens,
                    "out": tracker.output_tokens,
                    "reasoning": tracker.reasoning_tokens,
                })
                
                if attempt == 0:
                    telemetry["first_pass_structural_successes"] += 1
                    telemetry["llm_inference_latencies"].append(elapsed)
                
                return result
                
            except Exception as exc:
                err_msg = str(exc).lower()
                if "validation" in err_msg or "json" in err_msg or "pydantic" in err_msg:
                    if attempt == 0: telemetry["structural_failures"] += 1
                else:
                    if attempt == 0: telemetry["service_failures"] += 1

                if self._is_retryable_error(err_msg) and attempt < max_retries - 1:
                    if attempt == 0: telemetry["retry_loop_triggers"] += 1
                    time.sleep(initial_delay * (2 ** attempt))
                    continue
                raise

profiled_invoke_with_retry = ProfiledInvokeTracker()

class ProfiledTacticalScorer:
    def __call__(self, game, power):
        start = time.perf_counter()
        result = tactical_scorer_module.score_individual_orders(game, power)
        telemetry["tactical_scorer_latencies"].append(time.perf_counter() - start)
        return result

profiled_score_individual_orders = ProfiledTacticalScorer()

# Clean patching!
bot_module.invoke_with_retry = profiled_invoke_with_retry
handle_messages_module.invoke_with_retry = profiled_invoke_with_retry
evaluator_module.invoke_with_retry = profiled_invoke_with_retry
bot_module.score_individual_orders = profiled_score_individual_orders
handle_messages_module.score_individual_orders = profiled_score_individual_orders

class MockMap:
    def __init__(self):
        self.scs = ["LON", "EDI", "LVP", "PAR", "BRE", "MAR", "BUR", "PIC", "BEL", "HOL"]
    def abut_list(self, loc): return []

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

    def get_orders(self, power): return self._orders.get(power, [])
    def get_current_phase(self): return self.phase
    def get_phase_history(self) -> list: return []
    def get_all_possible_orders(self) -> dict: return self._possible_orders
    def get_orderable_locations(self, power) -> list: return self._orderable_locations.get(power, [])
    def get_units(self, power=None): return self._units if power is None else self._units.get(power, [])
    def get_centers(self, power=None): return self._centers if power is None else self._centers.get(power, [])
    def get_state(self) -> dict: return {"name": self.phase, "units": self._units, "centers": self._centers}

PROFILING_SUITE = [
    {
        "name": "Test 1: Standard DMZ Evaluation",
        "phase": "S1901M", "use_tactical": False,
        "units": {"ENGLAND": ["F LON", "A EDI"], "FRANCE": ["F BRE", "A PAR"], "GERMANY": ["A MUN"]},
        "centers": {"ENGLAND": ["LON", "EDI"], "FRANCE": ["PAR", "BRE"], "GERMANY": ["MUN"]},
        "orderable_locations": {"ENGLAND": ["LON", "EDI"], "FRANCE": ["BRE", "PAR"]},
        "possible_orders": {"LON": ["F LON - NTH", "F LON - ENG", "F LON H"], "EDI": ["A EDI H"], "BRE": ["F BRE H"], "PAR": ["A PAR H"]},
        "agreements": [{"id": 1, "bot_country": "FRANCE", "agreed_with": "ENGLAND", "agreement": "DMZ the English Channel."}],
        "orders": {"ENGLAND": ["F LON - NTH"], "FRANCE": ["F BRE - MAO"]},
        "sender": "ENGLAND", "recipient": "FRANCE", "message": "DMZ the English Channel."
    }
]

def _make_mock_game(run): return MockGame(run['phase'], run)

@patch('bot.evaluator.get_connection')
@patch('bot.evaluator.add_agreement')
@patch('bot.evaluator.update_agreement_status')
@patch('bot.evaluator.get_pending_agreements')
def run_benchmarks(mock_get_pending, mock_update_status, mock_add_agreement, mock_get_conn):
    print("=== Starting Isolated System Profiling Run ===\n")
    for run in PROFILING_SUITE:
        mock_game = _make_mock_game(run)
        mock_get_pending.return_value = run['agreements']
        
        _ = get_bot_messages(mock_game, run['sender'], bot_type="ai", game_id="prof_123", use_tactical=run['use_tactical'])
        _, _ = handle_incoming_message(game=mock_game, bot_name=run['recipient'], sender=run['sender'], message=run['message'], game_id="prof_123", recipient=run['recipient'], use_tactical=run['use_tactical'])
        _ = finalize_ai_bot_orders(mock_game, run['sender'], game_id="prof_123", use_tactical=run['use_tactical'])
        
        # Now intercepted properly!
        evaluate_agreements("prof_123", mock_game)

    print_final_telemetry()

def print_final_telemetry(bots_per_turn=7, estimated_agreements_per_turn=10):
    print("\n" + "="*95)
    print("                        COMPUTATIONAL COST & USAGE PROFILE")
    print("="*95)
    
    stats = defaultdict(lambda: {"in": 0, "cached": 0, "out": 0, "reasoning": 0, "cost": 0.0, "count": 0, "model": ""})
    for u in telemetry["usage"]:
        task = u["task"]
        stats[task]["in"] += u["in"]
        stats[task]["cached"] += u["cached"]
        stats[task]["out"] += u["out"]
        stats[task]["reasoning"] += u["reasoning"]
        stats[task]["cost"] += call_cost(u["model"], u["in"], u["cached"], u["out"])
        stats[task]["count"] += 1
        stats[task]["model"] = u["model"]
    
    print(f"{'Task':<20} | {'Model':<22} | {'In':<6} | {'Cached':<6} | {'Out':<6} | {'Reason':<6} | {'Cost/call ($)':<12}")
    print("-" * 95)
    
    bot_cost_per_turn = 0.0
    judge_cost_per_turn = 0.0

    for task, s in stats.items():
        if s["count"] == 0: continue
        avg_cost = s["cost"] / s["count"]
        
        if task == "Trust Evaluator":
            judge_cost_per_turn += (avg_cost * estimated_agreements_per_turn)
        else:
            bot_cost_per_turn += (avg_cost * bots_per_turn)
            
        print(f"{task:<20} | {s['model']:<22} | {int(s['in']/s['count']):<6} | {int(s['cached']/s['count']):<6} | {int(s['out']/s['count']):<6} | {int(s['reasoning']/s['count']):<6} | ${avg_cost:<11.5f}")

    print("-" * 95)
    print(f"Bot Fleet Cost / Turn (n={bots_per_turn} bots):        ${bot_cost_per_turn:.5f}")
    print(f"LLM Judge Cost / Turn (n={estimated_agreements_per_turn} treaties):    ${judge_cost_per_turn:.5f}")
    print(f"Total Projected Cost Per Full Turn:      ${(bot_cost_per_turn + judge_cost_per_turn):.5f}")
    print("=" * 95)
    
    print("\nSUB-ROUTINE BREAKDOWN (T = t_context + t_inference + t_heuristic)")
    print("-" * 80)
    def log_metric(label, data_list):
        if data_list:
            avg = sum(data_list) / len(data_list)
            print(f"{label:<32} Mean: {avg:6.4f}s | Max: {max(data_list):6.4f}s (n={len(data_list)})")
        else:
            print(f"{label:<32} No samples recorded.")

    log_metric("LLM Inf + Parse (t_inference):", telemetry["llm_inference_latencies"])
    log_metric("Tactical Scorer (t_heuristic):", telemetry["tactical_scorer_latencies"])

    total_calls = telemetry["structured_output_calls"]
    first_pass = telemetry["first_pass_structural_successes"]
    first_pass_rate = (first_pass / total_calls) * 100 if total_calls else 100.0
    
    print(f"\nLLM Structural Reliability: {first_pass_rate:.2f}% ({first_pass}/{total_calls} first-pass success)")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    run_benchmarks()