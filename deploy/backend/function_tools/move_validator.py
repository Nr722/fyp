from langchain_core.tools import tool
from diplomacy.engine.game import Game

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
