# """Quick experiment script: compare LLM decisions WITH and WITHOUT the tactical scorer."""
# import os
# import random
# import json
# from dotenv import load_dotenv
# from langchain_google_genai import ChatGoogleGenerativeAI
# from langchain_core.messages import HumanMessage, SystemMessage

# # Adjust imports to match your project structure
# from function_tools.tactical_scorer import score_individual_orders
# from bot.models import BotOrderResponse

# load_dotenv()

# def get_model(model_name="models/gemini-2.5-flash"):
#     return ChatGoogleGenerativeAI(model=model_name, google_api_key=os.getenv("GEMINI_API_KEY"))

# class MockMap:
#     def __init__(self):
#         self.scs = ['LON', 'BEL', 'PAR', 'BUR', 'MUN', 'VIE', 'TRI', 'BUL', 'GRE', 'CON']

#     def abut_list(self, loc):
#         adj = {
#             'LON': ['ENG', 'BEL'], 'BEL': ['LON', 'PIC', 'BUR', 'RUH'],
#             'PAR': ['BUR', 'PIC', 'BRE'], 'BUR': ['PAR', 'MUN', 'BEL'],
#             'MUN': ['BUR', 'KIE', 'BER'], 'TRI': ['VEN', 'BUD', 'ALB', 'ADR'],
#             'BUL': ['RUM', 'SER', 'CON', 'GRE'], 'GRE': ['ION', 'BUL', 'CON'],
#             'CON': ['BUL', 'GRE']
#         }
#         return adj.get(loc, [])

# class MockGame:
#     def __init__(self, orderable_locs, units, centers, possible_orders, phase='F1901M'):
#         self.map = MockMap()
#         self._orderable = orderable_locs
#         self._units = units
#         self._centers = centers
#         self._possible = possible_orders
#         self._phase = phase

#     def get_all_possible_orders(self): return self._possible
#     def get_orderable_locations(self, power): return self._orderable
#     def get_units(self, power=None): return self._units.get(power, []) if power else self._units
#     def get_centers(self, power): return self._centers.get(power, [])
#     def get_current_phase(self): return self._phase

# def build_scenarios():
#     return [
#         {
#             'name': 'France Opening (Western)', 'power': 'FRANCE',
#             'orderable': ['PAR', 'BRE', 'MAR'],
#             'units': {'FRANCE': ['A PAR', 'F BRE', 'A MAR'], 'ENGLAND': ['F ENG'], 'GERMANY': ['A MUN']},
#             'centers': {'FRANCE': ['PAR'], 'ENGLAND': ['LON'], 'GERMANY': ['MUN']},
#             'possible': {
#                 'PAR': ['A PAR - BUR', 'A PAR - PIC', 'A PAR H'],
#                 'BRE': ['F BRE - MAO', 'F BRE - PIC', 'F BRE H'],
#                 'MAR': ['A MAR - SPA', 'A MAR - BUR', 'A MAR H']
#             }
#         },
#         {
#             'name': 'Convoy Setup (England)', 'power': 'ENGLAND',
#             'orderable': ['ENG', 'LON'],
#             'units': {'ENGLAND': ['F ENG', 'A LON'], 'FRANCE': ['A BEL']},
#             'centers': {'ENGLAND': ['LON'], 'FRANCE': ['BEL']},
#             'possible': {
#                 'ENG': ['F ENG C A LON - BEL', 'F ENG - BEL', 'F ENG H'],
#                 'LON': ['A LON - BEL', 'A LON - NTH', 'A LON H']
#             }
#         },
#         {
#             'name': 'Balkans Bottleneck', 'power': 'AUSTRIA',
#             'orderable': ['TRI', 'VIE'],
#             'units': {'AUSTRIA': ['A TRI', 'A VIE'], 'ITALY': ['A VEN'], 'RUSSIA': ['A BUD'], 'TURKEY': ['A CON']},
#             'centers': {'AUSTRIA': ['VIE'], 'TURKEY': ['CON']},
#             'possible': {
#                 'TRI': ['A TRI - VEN', 'A TRI - ALB', 'A TRI H'],
#                 'VIE': ['A VIE S A TRI - VEN', 'A VIE - GAL', 'A VIE H']
#             }
#         },
#         {
#             'name': 'Clustered Midgame Fight', 'power': 'GERMANY',
#             'orderable': ['MUN', 'BER', 'KIE'],
#             'units': {'GERMANY': ['A MUN', 'A BER', 'A KIE'], 'FRANCE': ['A BUR'], 'RUSSIA': ['A WAR']},
#             'centers': {'GERMANY': ['MUN', 'BER']},
#             'possible': {
#                 'MUN': ['A MUN - BUR', 'A MUN H', 'A MUN S A BER - KIE'],
#                 'BER': ['A BER - KIE', 'A BER H', 'A BER S A MUN - BUR'],
#                 'KIE': ['A KIE - BER', 'A KIE - BAL', 'A KIE H']
#             }
#         },
#         {
#             'name': 'Support Cut Risk', 'power': 'FRANCE',
#             'orderable': ['BUR'],
#             'units': {'FRANCE': ['A BUR'], 'GERMANY': ['A MUN'], 'ENGLAND': ['F BEL']},
#             'centers': {'FRANCE': ['PAR']},
#             'possible': {
#                 'BUR': ['A BUR S A PAR - MAR', 'A BUR - MUN', 'A BUR H']
#             }
#         }
#     ]

# def rank_to_score(rank):
#     if rank is None: return 1
#     return max(1, 6 - rank)

# def simulate_llm_orders(game, game_cfg, include_tactical=True):
#     """Fetches orders from Gemini using your structured output schema."""
#     valid_orders = {loc: game.get_all_possible_orders().get(loc, []) for loc in game.get_orderable_locations(game_cfg['power'])}
    
#     system_prompt = f"You are playing Diplomacy as {game_cfg['power']}."
#     prompt = f"Board state (Units): {game_cfg['units']}\n"
#     prompt += f"Board state (Centers): {game_cfg['centers']}\n"

#     if include_tactical:
#         scored = score_individual_orders(game, game_cfg['power'])
#         tactical_context = "\nTACTICAL ANALYSIS (Top Orders per Unit):\n"
#         for loc, options in scored.items():
#             tactical_context += f"Unit {loc}:\n" + "".join([f"  - {opt['order']} (Score: {opt['score']})\n" for opt in options])
#         prompt += tactical_context
#         prompt += "\nConsider this tactical advice, but make your own final strategic decision."

#     prompt += f"\n\nAvailable Locations and Valid Options:\n{json.dumps(valid_orders, indent=2)}\n"

#     messages = [SystemMessage(content=system_prompt), HumanMessage(content=prompt)]
#     model = get_model().with_structured_output(BotOrderResponse)

#     orders = []
#     try:
#         data = model.invoke(messages)
#         # Map structured response back to orderable locations
#         order_dict = {o.location: o.order for o in data.orders}
#         for loc in game.get_orderable_locations(game_cfg['power']):
#             chosen = order_dict.get(loc)
#             if chosen in valid_orders.get(loc, []):
#                 orders.append(chosen)
#             else:
#                 orders.append(random.choice(valid_orders[loc]) if valid_orders[loc] else None)
#     except Exception as e:
#         print(f"LLM Error: {e}")
#         # Fallback if API fails
#         orders = [random.choice(valid_orders[loc]) if valid_orders.get(loc) else None for loc in game.get_orderable_locations(game_cfg['power'])]

#     return orders

# def run_trial(game_cfg, trials=2, seed=42):
#     random.seed(seed)
#     results = {'with_tactical': [], 'without_tactical': []}

#     for t in range(trials):
#         game = MockGame(game_cfg['orderable'], game_cfg['units'], game_cfg['centers'], game_cfg['possible'])
#         scored = score_individual_orders(game, game_cfg['power'])

#         # With tactical context
#         with_orders = simulate_llm_orders(game, game_cfg, include_tactical=True)
#         with_scores = []
#         for i, loc in enumerate(game.get_orderable_locations(game_cfg['power'])):
#             pick = with_orders[i] if i < len(with_orders) else None
#             rank = None
#             opts = scored.get(loc, [])
#             if pick and opts:
#                 for idx, o in enumerate(opts, start=1):
#                     if o['order'] == pick:
#                         rank = idx
#                         break
#             with_scores.append(rank_to_score(rank))

#         # Without tactical context (Baseline)
#         without_orders = simulate_llm_orders(game, game_cfg, include_tactical=False)
#         without_scores = []
#         for i, loc in enumerate(game.get_orderable_locations(game_cfg['power'])):
#             pick = without_orders[i] if i < len(without_orders) else None
#             rank = None
#             opts = scored.get(loc, [])
#             if pick and opts:
#                 for idx, o in enumerate(opts, start=1):
#                     if o['order'] == pick:
#                         rank = idx
#                         break
#             without_scores.append(rank_to_score(rank))

#         results['with_tactical'].append(with_scores)
#         results['without_tactical'].append(without_scores)

#     return results

# def summarize(all_results):
#     print("\nTactical Scorer Experiment Summary (Scores 1-5, higher is better):\n")
#     print(f"{'Scenario':30s} | {'LLM + Tactical':15s} | {'LLM Baseline':15s}")
#     print('-' * 66)
#     for name, res in all_results.items():
#         w = [sum(r) / len(r) for r in res['with_tactical']] if res['with_tactical'] else [0]
#         wo = [sum(r) / len(r) for r in res['without_tactical']] if res['without_tactical'] else [0]
        
#         avg_with = sum(w) / len(w) if w else 0
#         avg_without = sum(wo) / len(wo) if wo else 0
#         print(f"{name:30s} | {avg_with:<15.2f} | {avg_without:<15.2f}")

# def main():
#     scenarios = build_scenarios()
#     all_results = {}
    
#     # 3 trials per scenario per condition (30 API calls total)
#     for sc in scenarios:
#         print(f"Running scenario: {sc['name']}")
#         res = run_trial(sc, trials=3, seed=123)
#         all_results[sc['name']] = res

#     summarize(all_results)

# if __name__ == '__main__':
#     main()