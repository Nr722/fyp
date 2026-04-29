# --- Static Heuristic Scorer ---

def score_individual_orders(game, power):
    """
    Evaluates every possible order for every unit statically based on the current board.
    Returns a dictionary mapping each unit location to a ranked list of top orders.
    """
    valid_orders = game.get_all_possible_orders()
    orderable_locs = game.get_orderable_locations(power)
    
    # Build fast lookups
    my_centers = game.get_centers(power)
    all_centers = game.map.scs
    
    # Find all enemy unit locations
    enemy_units = []
    for p, units in game.get_units().items():
        if p != power:
            enemy_units.extend([u.split()[1][:3] for u in units])
            
    scored_options = {}
    
    for loc in orderable_locs:
        options = valid_orders.get(loc, ["HOLD"])
        scored_orders = []
        
        for order in options:
            score = 10 # Base score for just existing
            parts = order.split()
            
            # 1. Evaluate MOVE orders (e.g., "A PAR - BUR")
            if len(parts) >= 3 and parts[2] == "-":
                target = parts[3][:3]
                
                # Bonus for attacking/taking a Supply Center
                if target in all_centers and target not in my_centers:
                    score += 150 # HEAVILY weight moving to unowned supply centers
                    if target in enemy_units:
                        score += 50 # Attacking an ENEMY center is huge
                        
                # Bonus for attacking an enemy unit (non-center)
                elif target in enemy_units:
                    score += 50 
                
                # Bonus for moving closer to enemy units/action (Aggressive positioning)
                adj = game.map.abut_list(target)
                if any(a in enemy_units for a in adj):
                    score += 20
                
                # Bonus for moving to a highly tactical space (borders many supply centers)
                adj_scs = [a for a in adj if a in all_centers and a not in my_centers]
                score += len(adj_scs) * 20
                
                # Small penalty for just moving to boring empty space
                if score == 10:
                    score += 5 
                
            # 2. Evaluate SUPPORT orders (e.g., "A MUN S A BER - KIE" or "A MUN S A BER")
            elif " S " in order:
                target = parts[-1][:3] # Default to the final destination
                
                if target in all_centers and target not in my_centers:
                    score += 140 # Supporting an attack on an unowned/enemy center
                elif target in enemy_units:
                    score += 100 # Supporting an attack on an enemy unit
                else:
                    # Supporting own unit defensively or just holding ground
                    score += 20 
                    
            # 3. Evaluate HOLD orders (e.g., "A PAR H")
            elif " H" in order:
                # Holding a supply center is okay defensively
                if loc in my_centers:
                    score += 15
                # Holding a front line (adjacent to enemies) is good
                adj = game.map.abut_list(loc)
                if any(a in enemy_units for a in adj):
                    score += 30
            # 4. Evaluate CONVOY orders (e.g., "F ENG C A LON - BEL")
            elif " C " in order:
                # 'parts' looks like: ['F', 'ENG', 'C', 'A', 'LON', '-', 'BEL']
                target = parts[-1][:3] # The final destination of the convoyed Army
                
                # Bonus for convoying an army to take a Supply Center
                if target in all_centers and target not in my_centers:
                    score += 140 # Matches aggressive support value
                    if target in enemy_units:
                        score += 50 # Bonus if the center is occupied            
                # Bonus for convoying an attack on a regular enemy unit
                elif target in enemy_units:
                    score += 90 
                # General repositioning via water
                else:
                    score += 30
            scored_orders.append({"order": order, "score": score})
            
        # Sort the orders for this unit by score
        scored_orders.sort(key=lambda x: x["score"], reverse=True)
        # Only keep the top 4 most logical moves per unit
        scored_options[loc] = scored_orders[:4]
        
    print(f"\\n[Tactical Scorer] Evaluated individual orders for {power}:")
    for loc, options in scored_options.items():
        print(f"  Unit {loc}:")
        for opt in options:
            print(f"    -> {opt['order']} (Score: {opt['score']})")
        
    return scored_options