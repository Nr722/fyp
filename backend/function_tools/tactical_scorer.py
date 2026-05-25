# --- Static Heuristic Scorer ---

def score_individual_orders(game, power):
    """
    Evaluates every possible order for every unit statically based on the current board.
    Returns a dictionary mapping each unit location to a ranked list of top orders.
    """
    valid_orders = game.get_all_possible_orders()
    orderable_locs = game.get_orderable_locations(power)
    
    # Build fast lookups
    my_units_raw = game.get_units(power)
    my_units = [u.split()[1][:3] for u in my_units_raw]
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
                    score += 100 # Moderated down from 120 to allow positional setups to compete
                    if target in enemy_units:
                        score += 50 # Attacking an ENEMY center is huge
                        
                # Bonus for attacking an enemy unit (non-center)
                elif target in enemy_units:
                    score += 50 
                    
                # ---------------- NEW LOGIC ----------------
                # 1. Friendly Fire / Self-Bounce Penalty
                if target in my_units:
                    # severely penalize moving into a space we already occupy
                    score -= 80 
                    
                # 2. Unsupported vs Supported Attacks
                if target in enemy_units:
                    adj_to_target = game.map.abut_list(target)
                    friendly_potential_supports = len([u for u in my_units if u in adj_to_target and u != loc])
                    
                    if friendly_potential_supports == 0:
                        # Suicide attack against an occupied space with 0 support (1v1)
                        # Will likely bounce unless enemy vacates. Reduce the high enthusiasm.
                        score -= 60 
                    else:
                        # We have friends nearby! Good coordinated attack structure.
                        score += (friendly_potential_supports * 30)
                # -------------------------------------------
                
                # Bonus for moving closer to enemy units/action (Aggressive positioning)
                adj = game.map.abut_list(target)
                if any(a in enemy_units for a in adj):
                    score += 20
                
                # Bonus for moving to a highly tactical space (borders many supply centers)
                adj_scs = [a for a in adj if a in all_centers and a not in my_centers]
                score += len(adj_scs) * 20
                
                # ---------------- NEW LOGIC ----------------
                # 3. Anti-Convoy / Disruption Motivation
                SEA_ZONES = {'ENG', 'NTH', 'ION', 'BAL', 'BLA', 'EAS', 'WES', 'MAO', 'NAO', 'GOB', 'HEL', 'SKA', 'BAR', 'ADR', 'TYR'}
                if target in enemy_units and target in SEA_ZONES:
                    score += 40 # Disrupt enemy fleet / potential convoy
                # -------------------------------------------
                
                # Small penalty for just moving to boring empty space
                if score == 10:
                    score += 5 
                
            # 2. Evaluate SUPPORT orders (e.g., "A MUN S A BER - KIE" or "A MUN S A BER")
            elif " S " in order:
                target = parts[-1][:3] # Default to the final destination
                
                if target in all_centers and target not in my_centers:
                    score += 100 # Supporting an attack on an unowned/enemy center
                elif target in enemy_units:
                    score += 90 # Supporting an attack on an enemy unit
                else:
                    # Supporting own unit defensively or just holding ground
                    score += 30 
                    
                # ---------------- NEW LOGIC ----------------
                # Cut Support Risk
                adj = game.map.abut_list(loc)
                enemy_neighbors = [a for a in adj if a in enemy_units]
                if len(enemy_neighbors) > 0:
                    score -= 25 * len(enemy_neighbors) # Risk of being cut
                # -------------------------------------------
                    
            # 3. Evaluate HOLD orders (e.g., "A PAR H")
            elif " H" in order:
                # Holding a supply center is okay defensively
                if loc in my_centers:
                    score += 40
                # Holding a front line (adjacent to enemies) is good
                adj = game.map.abut_list(loc)
                enemy_neighbors = [a for a in adj if a in enemy_units]
                if len(enemy_neighbors) > 0:
                    score += 50
                    
                # ---------------- NEW LOGIC ----------------
                # Defensive Hold (Turtling)
                if len(enemy_neighbors) >= 2:
                    score += 80 # Heavy turtle bonus if outnumbered
                # -------------------------------------------
            # 4. Evaluate CONVOY orders (e.g., "F ENG C A LON - BEL")
            elif " C " in order:
                # 'parts' looks like: ['F', 'ENG', 'C', 'A', 'LON', '-', 'BEL']
                target = parts[-1][:3] # The final destination of the convoyed Army
                
                # Bonus for convoying an army to take a Supply Center
                if target in all_centers and target not in my_centers:
                    score += 150 # Slightly increased to encourage convoy maneuvers
                    if target in enemy_units:
                        score += 50 # Bonus if the center is occupied            
                # Bonus for convoying an attack on a regular enemy unit
                elif target in enemy_units:
                    score += 100 
                # General repositioning via water
                else:
                    score += 50
                    
            scored_orders.append({"order": order, "score": score})
            
        # Sort the orders for this unit by score
        scored_orders.sort(key=lambda x: x["score"], reverse=True)
        # Only keep the top 5 most logical moves per unit
        scored_options[loc] = scored_orders[:5]
        
    print(f"\\n[Tactical Scorer] Evaluated individual orders for {power}:")
    for loc, options in scored_options.items():
        print(f"  Unit {loc}:")
        for opt in options:
            print(f"    -> {opt['order']} (Score: {opt['score']})")
        
    return scored_options