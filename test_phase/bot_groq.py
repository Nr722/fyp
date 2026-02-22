from agents import Agent, Runner
from agents.extensions.models.litellm_model import LitellmModel
from agents.mcp import MCPServerStreamableHttp
import os
import asyncio
from dotenv import load_dotenv
load_dotenv()

# Global event loop to reuse across calls
_loop = None

def get_event_loop():
    """Get or create a persistent event loop."""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop

# ---------------------------------------------------------
# Async function to get AI orders
# ---------------------------------------------------------
async def get_ai_orders_async(power_name: str) -> dict:
    """
    Async function that connects to MCP server and generates orders.
    Returns: {"orders": [...], "raw": "..."}
    """
    try:
        async with MCPServerStreamableHttp(
            name="diplomacy_orders",
            params={
                "url": "http://localhost:8001/mcp",
            },
        ) as server:
            agent = Agent(
                name="diplomacy-ai",
                instructions="""You are an expert Diplomacy game AI assistant.
        
When asked to generate orders for a power:
1. First call get_phase() to see the current game phase
2. Call get_valid_orders(power=<power_name>) to get all legal moves
3. Analyze the valid orders and choose the best strategy
4. Call submit_orders(power=<power_name>, proposed_orders={...}) with your chosen orders
5. The proposed_orders should be a dict mapping unit location to full order string
   Example: {"A LON": "A LON - YOR", "F EDI": "F EDI - NTH"}

Always use the MCP tools to validate and submit orders.

Also explain briefly what your strategy for this turn is.
""",
                model=LitellmModel(
                    model="groq/llama-3.3-70b-versatile",
                    api_key=os.getenv("GROQ_API_KEY")
                ),
                mcp_servers=[server],
            )
            
            prompt = f"""Generate orders for {power_name} in the current Diplomacy game.

Steps:
1. Check the current phase
2. Get valid orders for {power_name}
3. Choose strategic orders
4. Submit them using submit_orders tool

Make sure to actually call the submit_orders tool with your chosen orders."""

            result = await Runner.run(agent, prompt)
            
            return {
                "orders": [],  # Orders will be read from file by main.py
                "raw": str(result)
            }
    except Exception as e:
        return {
            "orders": [],
            "raw": f"ERROR: {str(e)}"
        }

# ---------------------------------------------------------
# Synchronous wrapper for main.py
# ---------------------------------------------------------
def get_ai_orders_sync(game, power_name: str) -> dict:
    """
    Synchronous wrapper that runs the async function using a persistent event loop.
    The game object is passed but not used - MCP server reads from game_state.json
    """
    loop = get_event_loop()
    return loop.run_until_complete(get_ai_orders_async(power_name))


# ---------------------------------------------------------
# Test function
# ---------------------------------------------------------
if __name__ == "__main__":
    result = get_ai_orders_sync(None, "ENGLAND")
    print(result)
