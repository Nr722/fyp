
import os
import json
from diplomacy.engine.game import Game
from bot import get_ai_bot_orders, handle_incoming_message
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_ai_bot():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ Error: GEMINI_API_KEY not found in environment.")
        return

    print("🚀 Initializing test game (Standard Diplomacy)...")
    game = Game(map_name='standard')
    bot_name = "FRANCE"
    game_id = "test_game_123"

    print(f"\n--- Testing get_ai_bot_orders for {bot_name} ---")
    try:
        orders, messages = get_ai_bot_orders(game, bot_name, game_id=game_id)
        print(f"✅ AI Reasoning Strategy: (Check logs above)")
        print(f"✅ Orders received: {orders}")
        print(f"✅ Messages sent: {messages}")
        
        if not orders:
            print("⚠️ Warning: No orders were returned.")
    except Exception as e:
        print(f"❌ Error during get_ai_bot_orders: {e}")

    print(f"\n--- Testing handle_incoming_message for {bot_name} (PRIVATE) ---")
    sender = "ENGLAND"
    incoming_text = "Hello France, would you like to form an alliance against Germany? I'll support your move to Belgium."
    
    try:
        updated_orders, reaction_messages = handle_incoming_message(
            game, bot_name, sender, incoming_text, game_id=game_id, recipient=bot_name
        )
        print(f"✅ Reaction Messages: {reaction_messages}")
        if updated_orders is not None:
            print(f"✅ Updated Orders: {updated_orders}")
        else:
            print("ℹ️ Bot chose not to update orders.")
    except Exception as e:
        print(f"❌ Error during handle_incoming_message: {e}")

    print(f"\n--- Testing handle_incoming_message for {bot_name} (GLOBAL) ---")
    incoming_text_global = "ALL POWER: Let's all agree not to move into the Black Sea this turn."
    
    try:
        updated_orders, reaction_messages = handle_incoming_message(
            game, bot_name, sender, incoming_text_global, game_id=game_id, recipient="GLOBAL"
        )
        print(f"✅ Reaction Messages: {reaction_messages}")
    except Exception as e:
        print(f"❌ Error during handle_incoming_message: {e}")

if __name__ == "__main__":
    test_ai_bot()
