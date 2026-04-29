from langchain_core.tools import tool
from diplomacy.engine.game import Game

def check_internal_consistency(orders: list[str]) -> list[str]:
    """
    Checks a list of orders for internal consistency issues like self-bounces, 
    support mismatches, or convoy mismatches. Returns a list of error strings.
    """
    errors = []
    moves_to = {}
    ordered_actions = {}
    
    for order in orders:
        parts = order.split()
        if len(parts) < 2:
            continue
        unit_loc = parts[1].split('/')[0] # e.g. F SPA/SC -> SPA
        
        if " - " in order and " S " not in order and " C " not in order:
            dest = parts[-1].split('/')[0]
            if dest not in moves_to:
                moves_to[dest] = []
            moves_to[dest].append(order)
            ordered_actions[unit_loc] = ("MOVE", order)
        elif " S " in order:
            s_parts = order.split(" S ")
            if len(s_parts) > 1:
                target_info = s_parts[1]
                ordered_actions[unit_loc] = ("SUPPORT", target_info, order)
        elif " C " in order:
            c_parts = order.split(" C ")
            if len(c_parts) > 1:
                ordered_actions[unit_loc] = ("CONVOY", c_parts[1], order)
        else:
            ordered_actions[unit_loc] = ("OTHER", order)

    # Check for self-bounces
    for dest, move_orders in moves_to.items():
        if len(move_orders) > 1:
            errors.append(f"Self-bounce error: You ordered {len(move_orders)} units to move to {dest} ({', '.join(move_orders)}). This will result in a self-bounce unless one is intentionally arranged. Fix this.")

    # Check for support mismatches
    for loc, info in ordered_actions.items():
        if info[0] == "SUPPORT":
            target_info = info[1].strip()
            full_order = info[2]
            target_parts = target_info.split()
            if len(target_parts) > 1:
                target_loc = target_parts[1].split('/')[0]
                if target_loc in ordered_actions: # The supported unit is ours
                    target_action = ordered_actions[target_loc]
                    if " - " in target_info:
                        # Supporting a move
                        if target_action[0] != "MOVE" or target_action[1].strip() != target_info:
                            errors.append(f"Coordination mismatch: '{full_order}' supports a move, but the target unit is actually doing: '{target_action[-1]}'.")
                    else:
                        # Supporting a hold (or anything not moving)
                        if target_action[0] == "MOVE":
                            errors.append(f"Coordination mismatch: '{full_order}' supports a hold/non-move, but the target unit is moving: '{target_action[-1]}'.")
        
        elif info[0] == "CONVOY":
            target_info = info[1].strip()
            full_order = info[2]
            target_parts = target_info.split()
            if len(target_parts) > 1:
                target_loc = target_parts[1].split('/')[0]
                if target_loc in ordered_actions: # The convoyed unit is ours
                    target_action = ordered_actions[target_loc]
                    if target_action[0] != "MOVE" or target_action[1].strip() != target_info:
                         errors.append(f"Coordination mismatch: '{full_order}' attempts to convoy, but the target army is doing: '{target_action[-1]}'.")
                         
    return errors

def get_move_validator_tool(game: Game):
    """
    Creates a LangChain tool that captures the current game state 
    to validate a list of proposed orders.
    """
    @tool
    def validate_moves(orders: list[str]) -> str:
        """
        Validates a list of proposed Diplomacy orders for the current turn. 
        Provide a list of complete order strings (e.g., ["F Lyo - TYS", "A Par H"]).
        Returns a detailed report on whether each order is legal in the current game state.
        Use this tool to verify any proposals before making an agreement or submitting your turn.
        """
        print(f"[Move Validator Tool] Checking moves: {orders}")
        # Get all valid orders for all locations in the game currently
        valid_orders_dict = game.get_all_possible_orders()
        all_valid_orders = set()
        for loc, valid_list in valid_orders_dict.items():
            all_valid_orders.update(valid_list)
            
        report = []
        all_good = True
        for order in orders:
            # Check if precisely in the list of valid orders
            if order in all_valid_orders:
                report.append(f"'{order}': Valid")
            else:
                report.append(f"'{order}': INVALID (Not a legal move for any location in current phase)")
                all_good = False
        
        if all_good:
            print(f"[Move Validator Tool] Result: All {len(orders)} moves valid.")
            return "SUCCESS: All proposed orders are VALID for the current turn.\n" + "\n".join(report)
        print(f"[Move Validator Tool] Result: Found invalid moves.")
        return "WARNING: Some orders are INVALID in the current phase. Do not use the invalid ones:\n" + "\n".join(report)

    return validate_moves
