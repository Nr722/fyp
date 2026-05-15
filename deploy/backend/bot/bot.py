"""
Bot AI logic for the Diplomacy game.
"""
import random
import json
import os
import re
import time
from click import prompt
from dotenv import load_dotenv
import os
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from bot.models import BotTurnResponse, BotReactionResponse  # Import the model above
from diplomacy.engine.game import Game
from bot.random_bot import get_random_bot_orders
from bot.db import add_agreement, get_trust_history
from function_tools.move_validator import check_internal_consistency
from function_tools.tactial_scorer import score_individual_orders
load_dotenv()

# Dictionary to store chat histories for each bot in each game
chat_histories = {}

def get_model(model_name="models/gemini-3.1-flash-lite-preview"):
    # Note: Gemma models currently do not support JSON mode or structured outputs via the API.
    # We use a standard chat model and will handle the parsing manually if needed, 
    # or use a model that does support these features.
    return ChatGoogleGenerativeAI(model=model_name, google_api_key=os.getenv("GEMINI_API_KEY"))

def invoke_with_retry(model, history, max_retries=4, initial_delay=5, bot_name="Bot"):
    """Invokes the model with exponential backoff for RateLimit errors."""
    for attempt in range(max_retries):
        try:
            return model.invoke(history)
        except Exception as e:
            err_msg = str(e).lower()
            if "429" in err_msg or "rate limit" in err_msg or "quota" in err_msg or "resource_exhausted" in err_msg:
                if attempt < max_retries - 1:
                    delay = initial_delay * (2 ** attempt)
                    
                    # Gemini specifically tells us how long to wait ("Please retry in 45.44s")
                    match = re.search(r'retry in ([0-9.]+)s', err_msg)
                    if match:
                        try:
                            required_delay = float(match.group(1))
                            # Add a 2 second buffer to ensure we clear the limit window
                            delay = max(delay, required_delay + 2.0)
                        except ValueError:
                            pass
                            
                    # Use a very specific prefix that is hard to miss
                    print(f"DEBUG_TPM_LIMIT|{bot_name}|{delay:.1f}|{attempt + 1}")
                    time.sleep(delay)
                    continue
            raise e

def get_ai_bot_orders(game, bot_name: str, game_id: str = None):
    all_orders_dict = game.get_all_possible_orders()
    orderable_locs = game.get_orderable_locations(bot_name)
    phase = game.get_current_phase()
    
    if not orderable_locs:
        return [], []
        
    valid_orders = {loc: all_orders_dict.get(loc, []) for loc in orderable_locs}

    scored_options = score_individual_orders(game, bot_name)
    board_state = game.get_state()
    board_state_text = "\nCURRENT BOARD STATE:\n"
    for p in board_state.get('units', {}).keys():
        units = board_state['units'].get(p, [])
        centers = board_state['centers'].get(p, [])
        board_state_text += f"- {p}: {len(centers)} Supply Centers ({', '.join(centers)}), {len(units)} Units ({', '.join(units)})\n"
    tactical_context = "\
TACTICAL ANALYSIS (Top Individual Orders Per Unit based on map control and enemy adjacencies):\\n"
    for loc, options in scored_options.items():
        tactical_context += f"Unit {loc}:\\n"
        for opt in options:
            tactical_context += f"  - Order: {opt['order']} (Score: {opt['score']})\\n"

    prev_turn_text = ""
    past_phases = game.get_phase_history()
    if past_phases:
        last_phase = past_phases[-1]
        prev_turn_text = f"\nPREVIOUS PHASE ({last_phase.name}) ORDERS:\n"
        last_orders = getattr(last_phase, 'orders', {})
        has_orders = False
        for p, p_orders in last_orders.items():
            if p_orders:
                prev_turn_text += f"- {p}: {', '.join(p_orders)}\n"
                has_orders = True
        if not has_orders:
            prev_turn_text += "No active orders were submitted in the previous phase.\n"
            
        last_results = getattr(last_phase, 'results', {})
        prev_turn_text += "\nPREVIOUS PHASE RESULTS:\n"
        has_results = False
        for loc, res in last_results.items():
            if res:
                prev_turn_text += f"- {loc}: {', '.join([str(r) for r in res])}\n"
                has_results = True
        if not has_results:
            prev_turn_text += "No conflict/bouncing results in the previous phase.\n"

    trust_history_text = ""
    if game_id:
        from bot.db import get_connection
        try:
            # Quick hack to get all past agreements for this bot in this game
            conn = get_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT agreed_with, agreement, followed, phase_made
                    FROM trust_ledger WHERE game_id=%s AND bot_country=%s AND followed IS NOT NULL
                """, (game_id, bot_name))
                history_rows = cur.fetchall()
            conn.close()
            if history_rows:
                trust_history_text = "\nTRUST LEDGER (Past agreements and whether the other country followed them):\n"
                for row in history_rows:
                    status = "FOLLOWED" if row[2] else "BROKEN"
                    trust_history_text += f"- {row[0]} {status} agreement made in {row[3]}: '{row[1]}'\n"
        except Exception as e:
            pass

    # IMPORTANT: You MUST respond with a JSON object exactly matching this schema:
    # {BotTurnResponse.model_json_schema()}
    # Unique key combining the game and the specific bot
    session_key = f"{game_id}_{bot_name}"

    # Initialize chat history if not exists
    if session_key not in chat_histories:
        print(f"Creating new history for {session_key}")
        
        system_prompt = f"""We are playing the board game Diplomacy. You are {bot_name}.
You are a pragmatic, highly competitive human player in an online tournament. You type quickly using lowercase, abbreviations, and sentence fragments (e.g., "rum", "east med", "bounce", "dmz"). Maintain a confident, unapologetic, and direct tone. Ensure your survival by forging alliances, staying paranoid, and seeking tactical advantages.

STRICT RULES:
1. ORDER LIMIT: Provide exactly ONE valid order for every unit location listed.
2. SYNTAX: Match the exact spelling and format from 'Valid Options'. Select ONLY from these provided options.
3. CONVOYS: Pair every Army 'VIA' order with a corresponding Fleet 'C' (Convoy) order in the same turn, or secure a firm agreement for an ally to convoy you.
4. SUPPORT: Only issue a support order if the target unit is genuinely executing the specified move.
5. COORDINATION: Form a cohesive plan across all your units. Plan distinct destinations for each unit to avoid unintentional self-bounces.
6. SECRECY & MISDIRECTION: Guard your true tactical orders aggressively. You are playing for yourself. Use the 'messages' to probe for information, float lies, or propose conditional teamwork. NEVER unilaterally declare your true and exact 'orders' to your neighbors before the turn resolves. If you want to talk about taking a territory, propose it as a question or condition (e.g., "if u hit bur, ill hit pic"), rather than a broadcast of reality.
7. BOARD AWARENESS: Ground all proposed moves and messages in the firm reality of the CURRENT BOARD STATE. Verify territory ownership and adjacencies before speaking.
8. COMMUNICATION STYLE:
- Brevity: Use brief fragments and lowercase text (e.g., "bud-ser?", "ill support u to bel").
- Inquiry: Focus on asking other players about their plans rather than declaring your own ("whats the play?", "u taking serbia?").
- Confidence: Speak plainly and decisively without offering apologies or consolations.

CRITICAL: In your 'messages', DO NOT copy-paste or announce the exact moves you decided on in your 'orders'. If your 'orders' say A MUN - BUR, do not send a message saying "I am taking bur". Be cryptic.
{json.dumps(BotTurnResponse.model_json_schema(), indent=2)}
"""
        chat_histories[session_key] = [SystemMessage(content=system_prompt)]
        # chat_histories[session_key] = [
        #             HumanMessage(content=system_prompt),
        #             AIMessage(content="I understand the rules and my persona. I am a ruthless competitor aiming for 18 supply centers. I will format my responses as instructed.")
        #         ]
        
    prompt = f"""Current Phase: {phase}
    {board_state_text}
    {prev_turn_text}
    
    {trust_history_text}
    
    {tactical_context}
    
    Available Locations and Valid Options:
    {json.dumps(valid_orders, indent=2)}
    
    REMINDER: Generate your 'orders' array first. Then, when generating your 'messages' array, DO NOT simply announce those orders to other players. Distract, ask questions, or propose conditional trades instead.
    """

    history = chat_histories[session_key]
    
    model = get_model()
    structured_model = model.with_structured_output(BotTurnResponse)
    
    try:
        # Add the prompt to history
        history.append(HumanMessage(content=prompt))
        
        # Loop to enforce JSON structured output
        data = None
        for parse_attempt in range(3):
            # Use our retry loop with the structured model
            response = invoke_with_retry(structured_model, history, bot_name=bot_name)
            
            # The response is now directly a BotTurnResponse object
            data = response
            
            # Check for self-bounces, internal consistency, and basic syntax validity
            if data and data.orders:
                temp_orders = [o.order for o in data.orders if o.order]
                
                consistency_errors = check_internal_consistency(temp_orders)
                
                # Also check if the AI submitted strictly valid engine strings
                for item in data.orders:
                    loc = item.location
                    order_str = item.order
                    if loc and order_str:
                        if loc not in valid_orders:
                            consistency_errors.append(f"Invalid unit location: {loc}. You do not have a unit there that can take orders.")
                        elif order_str not in valid_orders.get(loc, []):
                            consistency_errors.append(f"Invalid order syntax for {loc}: '{order_str}'. This exact string is not in your allowed 'Valid Options'.")
                            
                if consistency_errors:
                    err_str = " ".join(consistency_errors)
                    print(f"[{bot_name}] Validation Check Failed: {err_str}")
                    history.append(AIMessage(content=json.dumps(data.model_dump())))
                    history.append(HumanMessage(content=f"Your proposed orders have errors. Fix these exact issues before submitting:\n{err_str}"))
                    data = None
                    continue

            break # Successfully validated!

        if not data:
            raise ValueError("Failed to get valid JSON from model after multiple attempts.")
        
        # Add AI message to history
        history.append(AIMessage(content=json.dumps(data.model_dump())))

        strategy = data.reasoning
        print(f"[{bot_name} Strategy]: {strategy}")

        final_orders = []
        # Access using object attributes
        orders_data = data.orders or []
        
        for item in orders_data:
            loc = item.location
            order_str = item.order
            
            if loc and order_str and order_str in valid_orders.get(loc, []):
                final_orders.append(order_str)
            elif loc and valid_orders.get(loc):
                # Fallback to the first valid order if the specific one is wrong
                final_orders.append(valid_orders[loc][0])

        messages = []
        messages_list = data.messages or []
        for item in messages_list:
            recipient = item.recipient
            message = item.message
            if recipient and message:
                messages.append({"recipient": recipient, "message": message})

        return final_orders, messages

    except Exception as e:
        print(f"AI Bot Error for {bot_name}: {e}")
        # Use random fallback
        return get_random_bot_orders(game, bot_name)
    
def get_bot_orders(game, bot_name, bot_type="random", game_id=None):
    if bot_type == "ai" and game_id is not None:
        return get_ai_bot_orders(game, bot_name, game_id=game_id)
    return get_random_bot_orders(game, bot_name)

if __name__ == "__main__":
    from diplomacy.engine.game import Game

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print(" Error: GEMINI_API_KEY not found in environment.")
    else:
        print(" API Key found. Initializing test game...")
        
        # 1. Create a real game instance for the test
        test_game = Game(map_name='standard')
        test_bot = "FRANCE"
        
        print(f" Requesting AI orders for {test_bot}...")
        
        try:
            # 2. Call the function with the instance
            orders = get_ai_bot_orders(test_game, game_id="test_game", bot_name=test_bot)
            
            print("\n--- Test Results ---")
            print(f"Status: Success")
            print(f"Orders received: {orders}")
        except Exception as e:
            print(f"\n--- Test Failed ---")
            print(f"Error Type: {type(e).__name__}")
            print(f"Error Message: {e}")

