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
            score = 10 # Base score
            parts = order.split()
            
            # 1. Evaluate MOVE orders (e.g., "A PAR - BUR")
            if len(parts) >= 3 and parts[2] == "-":
                target = parts[3][:3]
                
                # Bonus for attacking/taking an unowned or enemy Supply Center
                if target in all_centers and target not in my_centers:
                    score += 100 
                    if target in enemy_units:
                        score += 50 
                        
                # Bonus for attacking an enemy unit (non-center)
                elif target in enemy_units:
                    score += 50 
                    
                # FIX 1: Openings / Vacating home centers to expand
                if loc in my_centers and target not in my_units:
                    # Encourage clearing out of home centers so new builds can happen
                    score += 45 
                    
                # Friendly Fire / Self-Bounce Penalty
                if target in my_units:
                    score -= 80 
                    
                # Unsupported vs Supported Attacks
                if target in enemy_units:
                    adj_to_target = game.map.abut_list(target)
                    friendly_potential_supports = len([u for u in my_units if u in adj_to_target and u != loc])
                    
                    if friendly_potential_supports == 0:
                        score -= 60 
                    else:
                        score += (friendly_potential_supports * 30)
                
                # FIX 2: Increase value of positioning closer to action/borders
                adj = game.map.abut_list(target)
                if any(a in enemy_units for a in adj):
                    score += 35 # Up from 20
                
                # Value of moving to spaces adjacent to unowned centers
                adj_scs = [a for a in adj if a in all_centers and a not in my_centers]
                score += len(adj_scs) * 30 # Up from 20
                
                # Anti-Convoy / Disruption Motivation
                SEA_ZONES = {'ENG', 'NTH', 'ION', 'BAL', 'BLA', 'EAS', 'WES', 'MAO', 'NAO', 'GOB', 'HEL', 'SKA', 'BAR', 'ADR', 'TYR'}
                if target in enemy_units and target in SEA_ZONES:
                    score += 40 
                
                # Small penalty for just moving to boring empty space reduced
                if score == 10:
                    score += 5 
                
            # 2. Evaluate SUPPORT orders
            elif " S " in order:
                target = parts[-1][:3] 
                
                if target in all_centers and target not in my_centers:
                    score += 100 
                elif target in enemy_units:
                    score += 90 
                else:
                    score += 30 
                    
                # Cut Support Risk
                adj = game.map.abut_list(loc)
                enemy_neighbors = [a for a in adj if a in enemy_units]
                if len(enemy_neighbors) > 0:
                    score -= 25 * len(enemy_neighbors)
                    
            # 3. Evaluate HOLD orders
            elif " H" in order or order.endswith("H"):
                adj = game.map.abut_list(loc)
                enemy_neighbors = [a for a in adj if a in enemy_units]
                
                # FIX 3: Scale defense based on actual danger, not just existing on an SC
                if loc in my_centers:
                    if len(enemy_neighbors) == 0:
                        score += 15 # Low bonus if completely safe (allows expansion moves to beat it)
                    else:
                        score += 40 # Standard defensive bonus if enemies are nearby
                        
                if len(enemy_neighbors) > 0:
                    score += 40
                if len(enemy_neighbors) >= 2:
                    score += 60 
                    
            # 4. Evaluate CONVOY orders
            elif " C " in order:
                target = parts[-1][:3]
                if target in all_centers and target not in my_centers:
                    score += 150 
                    if target in enemy_units:
                        score += 50             
                elif target in enemy_units:
                    score += 100 
                else:
                    score += 50
                    
            scored_orders.append({"order": order, "score": score})
            
        scored_orders.sort(key=lambda x: x["score"], reverse=True)
        scored_options[loc] = scored_orders[:5]
        
    return scored_options