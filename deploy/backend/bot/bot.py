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
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from bot.models import BotTurnResponse, BotReactionResponse  # Import the model above
from diplomacy.engine.game import Game
from bot.random_bot import get_random_bot_orders
from bot.db import add_agreement, get_trust_history
from function_tools.move_validator import get_move_validator_tool
load_dotenv()

# Dictionary to store chat histories for each bot in each game
chat_histories = {}

def get_model(model_name="models/gemini-3.1-flash-lite-preview"):
    # Note: Gemma models currently do not support JSON mode or structured outputs via the API.
    # We use a standard chat model and will handle the parsing manually if needed, 
    # or use a model that does support these features.
    return ChatGoogleGenerativeAI(model=model_name, google_api_key=os.getenv("GEMINI_API_KEY"))

def invoke_agent_loop(model, tools, history, bot_name="Bot"):
    """
    Invokes the model with exponential backoff and automatically handles tool calls in a loop
    until the model returns a final text/JSON response.
    """
    tool_map = {t.name: t for t in tools}
    model_with_tools = model.bind_tools(tools)
    
    while True:
        response = invoke_with_retry(model_with_tools, history, bot_name=bot_name)
        history.append(response)
        
        # If the LLM called a tool
        if hasattr(response, 'tool_calls') and len(response.tool_calls) > 0:
            for tool_call in response.tool_calls:
                name = tool_call['name']
                print(f"[{bot_name} Tool Call]: {name}({tool_call['args']})")
                
                if name in tool_map:
                    args = tool_call['args']
                    # Sometimes simple values are wrapped in dicts with keys matching param names
                    # extract the list if it's there
                    if 'orders' in args:
                        tool_result = tool_map[name].invoke(args)
                    else:
                        tool_result = tool_map[name].invoke(args)
                    
                    history.append(ToolMessage(tool_call_id=tool_call['id'], content=str(tool_result)))
        else:
            return response

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

    prompt = f"""
    You are an expert Diplomacy player controlling {bot_name}.
    Current Phase: {phase}

    STRICT RULES:
    1. Provide exactly ONE order for every location listed.
    2. Choose ONLY from the 'Valid Options' provided.
    3. If you want to collaborate with other players, you can include messages to them. But you MUST still provide your orders based on the current game state.    
    
    {trust_history_text}
    
    Available Locations and Valid Options:
    {json.dumps(valid_orders, indent=2)}

    IMPORTANT: You MUST respond with a JSON object exactly matching this schema:
    {BotTurnResponse.model_json_schema()}
    """
    # Unique key combining the game and the specific bot
    session_key = f"{game_id}_{bot_name}"

    # Initialize chat history if not exists
    if session_key not in chat_histories:
        print(f"Creating new history for {session_key}")
        chat_histories[session_key] = []

    history = chat_histories[session_key]
    
    move_validator_tool = get_move_validator_tool(game)
    tools = [move_validator_tool]
    model = get_model()
    
    try:
        # Add the prompt to history
        history.append(HumanMessage(content=prompt))
        
        # Use our new agent loop
        response = invoke_agent_loop(model, tools, history, bot_name=bot_name)
        
        # Parse the response text
        raw_text = response.content
        if isinstance(raw_text, list):
            raw_text = "".join(item.get("text", "") if isinstance(item, dict) else str(item) for item in raw_text)
        else:
            raw_text = str(raw_text)
            
        match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if match:
            data_dict = json.loads(match.group(0))
        else:
            data_dict = json.loads(raw_text)
            
        data = BotTurnResponse(**data_dict)
        
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

