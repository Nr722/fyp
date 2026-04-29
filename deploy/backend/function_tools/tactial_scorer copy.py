import math
import itertools
from copy import deepcopy

# --- Helpers ---
def generate_legal_sets(game, power, max_combos=20):
    valid_orders = game.get_all_possible_orders()
    orderable_locs = game.get_orderable_locations(power)
    if not orderable_locs:
        return [[]]
    options = [valid_orders.get(loc, ["HOLD"]) for loc in orderable_locs]
    # For performance, if a player has many units, this can explode. We limit to a random sample or top if needed.
    # To keep it simple, we use itertools product. Be careful with many units.
    all_combos = list(itertools.product(*options))
    import random
    if len(all_combos) > max_combos:
        all_combos = random.sample(all_combos, max_combos)
    return all_combos

class DummyAdjudicator:
    def resolve(self, game, orders_dict):
        # Create a deep copy of the game to simulate
        cloned = deepcopy(game)
        cloned.clear_orders()
        
        # Set orders for each power specified
        for power, orders in orders_dict.items():
            cloned.set_orders(power, list(orders))
            
        # Process the turn with the diplomacy engine
        cloned.process()
        return cloned

# --- 1. The Heuristic Evaluator ---
def evaluate_state(board_state, target_power):
    """
    Scores the board state from the perspective of the target_power.
    Expand this with positional weights (e.g., +50 for chokepoints).
    """
    score = len(board_state.get_centers(target_power)) * 1000 
    
    # Add points for unit placement and survival
    for unit in board_state.get_units(target_power):
        # A unit string looks like 'A MAR' or 'F LON'
        parts = unit.split()
        if len(parts) > 1:
            loc = parts[1][:3] # Extract the 3-letter province code
            if loc in board_state.map.scs:
                score += 100 # Bonus for physically occupying *any* Supply Center
                
        score += 10 # Small base value for having a unit alive
        
    return score


# --- 2. The Softmax Math ---
def calculate_softmax_probabilities(scored_moves, temperature=1.0):
    """Converts raw enemy heuristic scores into a probability distribution."""
    if not scored_moves: return []
    
    # Subtract max score to prevent math.exp() overflow errors
    max_score = max(move['score'] for move in scored_moves)
    
    exp_scores = []
    for move in scored_moves:
        # Avoid division by zero if temperature is 0
        t = max(temperature, 0.01)
        exp_val = math.exp((move['score'] - max_score) / t)
        exp_scores.append({'orders': move['orders'], 'exp_val': exp_val})
        
    sum_exp = sum(item['exp_val'] for item in exp_scores)
    
    # Calculate final percentage (0.0 to 1.0)
    for item in exp_scores:
        item['probability'] = item['exp_val'] / sum_exp
        del item['exp_val']
        
    return exp_scores

# --- 3. Enemy Prediction ---
def get_probable_enemy_moves(board_state, enemy_power, adjudicator, temperature=1.0, max_combos=10):
    """Steps into the enemy's shoes to calculate what they are likely to do."""
    enemy_legal_sets = generate_legal_sets(board_state, enemy_power, max_combos=max_combos) # Your generator
    scored_moves = []
    
    for enemy_orders in enemy_legal_sets:
        # Resolve assuming other players hold (baseline simulation)
        orders_dict = {enemy_power: enemy_orders}
        future_state = adjudicator.resolve(board_state, orders_dict)
        
        # Evaluate from the ENEMY'S perspective
        score = evaluate_state(future_state, enemy_power)
        scored_moves.append({"orders": enemy_orders, "score": score})
        
    return calculate_softmax_probabilities(scored_moves, temperature)

# --- 4. The Main Tactical Filter ---
def get_top_tactical_moves(board_state, my_power, enemy_power, adjudicator, top_n=5, temperature=1.0, depth=2, verbose=True):
    """
    Calculates the Expected Value (EV) of your moves against probable enemy play.
    Returns the top 'N' moves to feed into your LLM.
    """
    # Scale down computational footprint based on depth to prevent endless-loop timeouts
    eval_combos = 20 if depth > 1 else 5
    enemy_combos = 10 if depth > 1 else 3
    
    if verbose:
        print(f"\\n[Tactical Scorer] Starting evaluation for {my_power} vs {enemy_power} (Depth: {depth})")
    
    my_legal_sets = generate_legal_sets(board_state, my_power, max_combos=eval_combos)
    
    if verbose:
        print(f"[Tactical Scorer] Generated {len(my_legal_sets)} possible order sets for {my_power}")
    
    enemy_probabilities = get_probable_enemy_moves(board_state, enemy_power, adjudicator, temperature, max_combos=enemy_combos)
    
    # Performance optimization: only consider the top most likely enemy moves
    enemy_probabilities.sort(key=lambda x: x["probability"], reverse=True)
    enemy_probabilities = enemy_probabilities[:5]
    
    # Re-normalize probabilities
    prob_sum = sum(move["probability"] for move in enemy_probabilities)
    if prob_sum > 0:
        for move in enemy_probabilities:
            move["probability"] /= prob_sum
            
    if verbose:
        print(f"[Tactical Scorer] Top {len(enemy_probabilities)} predicted moves for {enemy_power}:")
        for i, emp in enumerate(enemy_probabilities):
            print(f"  {i+1}. {emp['orders']} (Prob: {emp['probability']:.2f})")
    
    evaluated_options = []

    for my_orders in my_legal_sets:
        expected_value = 0
        
        # Test your move against every mathematically probable enemy move
        for enemy_move in enemy_probabilities:
            orders_dict = {
                my_power: my_orders,
                enemy_power: enemy_move["orders"]
            }
            future_state = adjudicator.resolve(board_state, orders_dict)
            
            # Evaluate from YOUR perspective
            outcome_score = evaluate_state(future_state, my_power)
            
            # EV = Outcome Score * Probability of it happening
            expected_value += (outcome_score * enemy_move["probability"])
            
        evaluated_options.append({
            "orders": my_orders, 
            "ev": expected_value
        })
        
    # Sort by highest Expected Value for Depth 1
    evaluated_options.sort(key=lambda x: x["ev"], reverse=True)
    best_options = evaluated_options[:top_n]
    
    if verbose:
        print(f"\\n[Tactical Scorer] Top {len(best_options)} moves after Depth 1 Eval:")
        for i, opt in enumerate(best_options):
            print(f"  {i+1}. {opt['orders']} (EV: {opt['ev']:.2f})")
        
    # Depth 2 Lookahead
    if depth > 1:
        if verbose:
            print(f"\\n[Tactical Scorer] Expanding top candidates to Depth {depth}...")
            
        for option in best_options:
            advanced_ev = 0
            best_followups = []
            
            for enemy_move in enemy_probabilities:
                orders_dict = {
                    my_power: option["orders"],
                    enemy_power: enemy_move["orders"]
                }
                future_state = adjudicator.resolve(board_state, orders_dict)
                
                # Recursively call for the next turn (depth-1) from the future state.
                # We only need the top 1 move to determine our max expected value from that state.
                future_moves = get_top_tactical_moves(future_state, my_power, enemy_power, adjudicator, top_n=1, temperature=temperature, depth=depth-1, verbose=False)
                
                if future_moves:
                    advanced_ev += (future_moves[0]["ev"] * enemy_move["probability"])
                    best_followups.append(future_moves[0]["orders"])
                else:
                    advanced_ev += (evaluate_state(future_state, my_power) * enemy_move["probability"])
                    
            # Overwrite the depth 1 EV with the refined depth 2 EV
            option["depth_1_ev"] = option["ev"]
            option["ev"] = advanced_ev
            if best_followups:
                # Store the most likely follow-up move as an example of the tactic
                option["expected_followup"] = best_followups[0]
                
            if verbose:
                print(f"  -> Depth {depth} eval for {option['orders']}: New EV = {advanced_ev:.2f}, Expected Followup = {option.get('expected_followup', 'None')}")
            
        # Re-sort the top options based on their depth 2 EV
        best_options.sort(key=lambda x: x["ev"], reverse=True)
        
        if verbose:
            print(f"\\n[Tactical Scorer] Final Depth {depth} Selection:")
            for idx, opt in enumerate(best_options):
                print(f"  {idx+1}. {opt['orders']} (EV: {opt['ev']:.2f})")
    
    return best_options