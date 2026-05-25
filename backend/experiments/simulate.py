import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from diplomacy.engine.game import Game
from function_tools.db import init_db
from bot.bot import get_bot_messages, get_bot_orders, finalize_ai_bot_orders
from bot.handle_messages import handle_incoming_message
from bot.evaluator import evaluate_agreements
import json
import time

# Define the split: 4 with tactical, 3 without
TACTICAL_POWERS = ["ENGLAND", "FRANCE", "GERMANY", "ITALY"]
BASELINE_POWERS = ["AUSTRIA", "RUSSIA", "TURKEY"]

def run_simulation(game_name, max_phases=15):
    print(f"Starting simulation: {game_name}")
    init_db()
    game = Game()
    game_id = game_name
    
    powers = TACTICAL_POWERS + BASELINE_POWERS
    history_log = []
    
    for _ in range(max_phases):
        phase = game.get_current_phase()
        print(f"\n--- Phase: {phase} ---")
        
        phase_messages = []
        
        # 1. MESSAGE EXCHANGES
        print("Starting Negotiation Phase...")
        for sender in powers:
            if game.powers[sender].is_eliminated():
                continue
                
            print(f"{sender} is initiating messages...")
            has_tactical = sender in TACTICAL_POWERS
            
            # Pass use_tactical flag
            out_msgs = get_bot_messages(game, sender, bot_type="ai", game_id=game_id, use_tactical=has_tactical)
            
            for msg_obj in out_msgs:
                recipient = msg_obj["recipient"]
                content = msg_obj["message"]
                
                print(f"[{sender} -> {recipient}]: {content}")
                phase_messages.append({"sender": sender, "recipient": recipient, "message": content, "type": "initial"})
                
                if recipient in powers and not game.powers[recipient].is_eliminated():
                    recipient_has_tactical = recipient in TACTICAL_POWERS
                    # Ensure your handle_incoming_message function accepts use_tactical
                    reply_orders, replies = handle_incoming_message(
                        game=game, 
                        bot_name=recipient, 
                        sender=sender, 
                        message=content, 
                        game_id=game_id, 
                        recipient=recipient,
                        use_tactical=recipient_has_tactical 
                    )
                    
                    if replies:
                        for r_msg in replies:
                            print(f"[REPLY] [{recipient} -> {r_msg['recipient']}]: {r_msg['message']}")
                            phase_messages.append({"sender": recipient, "recipient": r_msg['recipient'], "message": r_msg['message'], "type": "reply"})
        
        # 2. ORDER FINALIZATION
        print("\nFinalizing Orders...")
        phase_orders = {}
        for power in powers:
            if not game.powers[power].is_eliminated():
                has_tactical = power in TACTICAL_POWERS
                orders = finalize_ai_bot_orders(game, power, game_id, use_tactical=has_tactical)
                phase_orders[power] = orders
                game.set_orders(power, orders)
                print(f"{power} final orders: {orders}")
        
        # 3. PROCESS PHASE
        print(f"\nProcessing Turn {phase}...")
        game.process()
        
        # 4. EVALUATE AGREEMENTS
        print("Evaluating Agreements...")
        evaluate_agreements(game_id, game)
        
        # Record state
        history_log.append({
            "phase": phase,
            "messages": phase_messages,
            "orders": phase_orders,
            "board": {
                "units": game.get_units(),
                "centers": game.get_centers()
            }
        })
        
        if game.is_game_done:
            print(f"Game finished! Winner: {game.outcome}")
            break

    with open(f"{game_name}_log.json", "w") as f:
        json.dump(history_log, f, indent=2)
    print(f"Simulation saved to {game_name}_log.json")

if __name__ == "__main__":
    import uuid
    run_simulation(f"sim_{uuid.uuid4().hex[:8]}")
    