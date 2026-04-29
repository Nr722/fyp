from fastapi import FastAPI, HTTPException, BackgroundTasks
import asyncio
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uuid
import os
import json
import base64
import sys
import threading
import io
import time
from diplomacy.engine.game import Game
from diplomacy.engine.message import Message

# Import from backend module
from bot.db import init_db, save_message, get_game_messages
from bot.bot import get_bot_orders
from bot.handle_messages import handle_incoming_message
from bot.random_bot import get_random_bot_orders
from viz import generate_history_svg

app = FastAPI()

@app.on_event("startup")
def startup_event():
    init_db()

# In-memory store for games
games: Dict[str, Game] = {}
game_locks: Dict[str, threading.Lock] = {}
game_configs: Dict[str, Dict[str, Any]] = {}
rate_limit_events: List[Dict] = []

class CreateGameRequest(BaseModel):
    human_power: str
    num_ai_bots: int = 1

class OrderRequest(BaseModel):
    power: str
    orders: List[str]

class MessageRequest(BaseModel):
    sender: str
    recipient: str
    message: str
    phase: str

class ProcessTurnRequest(BaseModel):
    human_power: str
    phase: Optional[str] = None

@app.post("/game/new")
def create_game(req: CreateGameRequest):
    import random
    game_id = str(uuid.uuid4())
    game = Game(map_name='standard')
    games[game_id] = game
    
    # Assign AI bots
    powers = list(game.powers.keys())
    if req.human_power in powers:
        powers.remove(req.human_power)
    
    ai_powers = random.sample(powers, min(req.num_ai_bots, len(powers)))
    game_configs[game_id] = {"ai_powers": ai_powers}
    game_locks[game_id] = threading.Lock()
    
    # Start bot reasoning for the first phase!
    threading.Thread(target=run_bots_for_game, args=(game_id, req.human_power)).start()
    
    return {"game_id": game_id, "human_power": req.human_power, "ai_powers": ai_powers}

@app.get("/game/{game_id}/state")
def get_game_state(game_id: str):
    if game_id not in games:
        raise HTTPException(status_code=404, detail="Game not found")
    game = games[game_id]
    
    # Generate SVG map
    current_phase = game.get_current_phase()
    map_path = f"maps/board_{game_id}_{current_phase}.svg"
    os.makedirs('maps', exist_ok=True)
    game.render(incl_orders=False, incl_abbrev=True, output_path=map_path)
    with open(map_path, "r") as f:
        svg_content = f.read()
        
    # Generate history SVG if available
    hist_svg_content = None
    last_phase_name = None
    if game.get_phase_history():
        last_phase_name = list(game.get_phase_history())[-1].name
        hist_path = f"maps/history_{game_id}_{last_phase_name}.svg"
        generate_history_svg(game, hist_path)
        with open(hist_path, "r") as f:
            hist_svg_content = f.read()

    active_powers = [p for p, data in game.powers.items() if not data.is_eliminated()]
    
    return {
        "phase": current_phase,
        "powers": list(game.powers.keys()),
        "active_powers": active_powers,
        "units": game.get_units(),
        "centers": game.get_centers(),
        "is_game_done": game.is_game_done,
        "winner": game.outcome,
        "map_svg": svg_content,
        "history_svg": hist_svg_content,
        "last_phase_name": last_phase_name
    }

@app.get("/game/{game_id}/orders/possible/{power}")
def get_possible_orders(game_id: str, power: str):
    if game_id not in games:
        raise HTTPException(status_code=404, detail="Game not found")
    game = games[game_id]
    
    return {
        "orderable_locations": game.get_orderable_locations(power),
        "all_possible_orders": game.get_all_possible_orders(),
        "power_units": game.get_units(power)
    }

@app.post("/game/{game_id}/orders")
def submit_orders(game_id: str, req: OrderRequest):
    if game_id not in games:
        raise HTTPException(status_code=404, detail="Game not found")
    game = games[game_id]
    
    try:
        game.set_orders(req.power, req.orders)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/game/{game_id}/rate-limits")
def get_rate_limits(game_id: str):
    global rate_limit_events
    events = list(rate_limit_events)
    # rate_limit_events = [] # Clear after reading
    return {"events": events}

@app.post("/game/{game_id}/test-rate-limit")
def test_rate_limit(game_id: str):
    """Debug endpoint to fake a rate limit event."""
    rate_limit_events.append({
        "bot_name": "TEST_BOT",
        "delay": "10",
        "attempt": "1",
        "type": "debug",
        "timestamp": time.time()
    })
    return {"status": "Fake event queued"}

@app.post("/game/{game_id}/clear-rate-limits")
def clear_rate_limits(game_id: str):
    global rate_limit_events
    rate_limit_events = []
    return {"status": "Cleared"}

@app.post("/game/{game_id}/process")
def process_turn(game_id: str, req: ProcessTurnRequest):
    if game_id not in games:
        raise HTTPException(status_code=404, detail="Game not found")
    game = games[game_id]
    lock = game_locks.get(game_id)
    if not lock:
        raise HTTPException(status_code=500, detail="Lock missing")
        
    with lock:
        if req.phase and game.get_current_phase() != req.phase:
            return {
                "status": "success",
                "prev_phase": req.phase,
                "new_phase": game.get_current_phase(),
                "bot_orders": {}
            }
            
        bot_orders_dict = {}
        active_powers = [p for p, data in game.powers.items() if not data.is_eliminated()]
        bot_powers = [p for p in active_powers if p != req.human_power]
        for p in bot_powers:
            bot_orders_dict[p] = list(game.get_orders().get(p, []))
            
        from bot.evaluator import evaluate_agreements
        evaluate_agreements(game_id, game)
        
        prev_phase = game.get_current_phase()
        game.process()
        
    # Start bot reasoning for the new phase!
    threading.Thread(target=run_bots_for_game, args=(game_id, req.human_power)).start()
    
    return {
        "status": "success",
        "prev_phase": prev_phase,
        "new_phase": game.get_current_phase(),
        "bot_orders": bot_orders_dict
    }

@app.get("/game/{game_id}/messages")
def get_messages(game_id: str, power: str):
    if game_id not in games:
        raise HTTPException(status_code=404, detail="Game not found")
    
    # Fetch from NeonDB
    all_msgs = get_game_messages(game_id)
    
    msgs = []
    for msg in all_msgs:
        # Filter visibility
        if msg["recipient"] == "GLOBAL" or msg["sender"] == power or msg["recipient"] == power:
            msgs.append({
                "sender": msg["sender"],
                "recipient": msg["recipient"],
                "message": msg["message"],
                "phase": msg["phase"],
                "time_sent": int(msg["time_sent"].timestamp() * 1000000) if hasattr(msg["time_sent"], "timestamp") else 0
            })
    return {"messages": msgs}

def process_ai_reaction_task(game_id: str, sender: str, recipient: str, message: str, phase: str):
    if game_id not in games:
        return
    game = games[game_id]
    lock = game_locks.get(game_id)
    if not lock:
        return
        
    with lock:
        if game.get_current_phase() != phase:
            return
            
        config = game_configs.get(game_id, {"ai_powers": []})
        ai_powers = config.get("ai_powers", [])
        
        recipients = []
        if recipient == "GLOBAL":
            recipients = [p for p in ai_powers if p != sender]
        elif recipient in ai_powers:
            recipients = [recipient]
            
        for bot_name in recipients:
            try:
                import bot.bot as bot
                original_print = getattr(bot, 'print', print)
                def patched_print(*args, **kwargs):
                    msg = " ".join(map(str, args))
                    if "DEBUG_TPM_LIMIT|" in msg:
                        try:
                            parts = msg.split("DEBUG_TPM_LIMIT|")[1].split("|")
                            if len(parts) >= 3:
                                b_name, dly, att = parts[:3]
                                rate_limit_events.append({
                                    "bot_name": b_name,
                                    "delay": dly,
                                    "attempt": att,
                                    "type": "message",
                                    "timestamp": time.time()
                                })
                        except Exception as e:
                            original_print(f"Error parsing rate limit log: {e}")
                    original_print(*args, **kwargs)
            
                bot.print = patched_print
                from bot.handle_messages import handle_incoming_message
                try:
                    updated_orders, bot_messages = handle_incoming_message(
                        game=game,
                        bot_name=bot_name,
                        sender=sender,
                        message=message,
                        game_id=game_id,
                        recipient=recipient
                    )
                finally:
                    bot.print = original_print
            
                if updated_orders is not None:
                    game.set_orders(bot_name, updated_orders)
                
                if bot_messages:
                    from diplomacy.engine.message import Message
                    for msg_data in bot_messages:
                        reply_msg = Message(
                            sender=bot_name,
                            recipient=msg_data["recipient"],
                            message=msg_data["message"],
                            phase=game.get_current_phase()
                        )
                        game.add_message(reply_msg)
                        
                        # Save the bot's reaction message to NeonDB
                        save_message(game_id, bot_name, msg_data["recipient"], msg_data["message"], game.get_current_phase())
            except Exception as e:
                print(f"Error handling message for bot {bot_name}: {e}")

@app.post("/game/{game_id}/messages")
def send_message(game_id: str, req: MessageRequest, bg_tasks: BackgroundTasks):
    if game_id not in games:
        raise HTTPException(status_code=404, detail="Game not found")
    game = games[game_id]
    
    new_msg = Message(
        sender=req.sender,
        recipient=req.recipient,
        message=req.message,
        phase=req.phase
    )
    game.add_message(new_msg)
    
    # Save the human's message to NeonDB
    save_message(game_id, req.sender, req.recipient, req.message, req.phase)
    
    # Trigger AI reaction in the background
    bg_tasks.add_task(process_ai_reaction_task, game_id, req.sender, req.recipient, req.message, req.phase)
            
    return {"status": "success"}

if __name__ == "__main__":
    import uvicorn
    # Make sure 'uvicorn' is installed in your uv environment
    # 'server' refers to the filename server.py, 'app' is your FastAPI instance
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
def run_bots_for_game(game_id: str, human_power: str):
    if game_id not in games:
        return
    game = games[game_id]
    lock = game_locks.get(game_id)
    if not lock:
        return
        
    with lock:
        active_powers = [p for p, data in game.powers.items() if not data.is_eliminated()]
        bot_powers = [p for p in active_powers if p != human_power]
        
        config = game_configs.get(game_id, {"ai_powers": []})
        ai_powers = config.get("ai_powers", [])
        
        import bot.bot as bot
        try:
            original_print = getattr(bot, 'print', print)
            
            def patched_print(*args, **kwargs):
                msg = " ".join(map(str, args))
                if "DEBUG_TPM_LIMIT|" in msg:
                    try:
                        parts = msg.split("DEBUG_TPM_LIMIT|")[1].split("|")
                        if len(parts) >= 3:
                            b_name, dly, att = parts[:3]
                            rate_limit_events.append({
                                "bot_name": b_name,
                                "delay": dly,
                                "attempt": att,
                                "type": "order",
                                "timestamp": time.time()
                            })
                    except Exception as e:
                        original_print(f"Error parsing rate limit log: {e}")
                original_print(*args, **kwargs)
            
            bot.print = patched_print
            try:
                for bp in bot_powers:
                    try:
                        bot_type = "ai" if bp in ai_powers else "random"
                        bot_orders, bot_messages = get_bot_orders(game, bp, bot_type=bot_type, game_id=game_id)
                        game.set_orders(bp, bot_orders)
                        
                        if bot_messages:
                            for msg_data in bot_messages:
                                new_msg = Message(
                                    sender=bp,
                                    recipient=msg_data["recipient"],
                                    message=msg_data["message"],
                                    phase=game.get_current_phase()
                                )
                                game.add_message(new_msg)
                                save_message(game_id, bp, msg_data["recipient"], msg_data["message"], game.get_current_phase())
                    except Exception as e:
                        print(f"Bot {bp} failed to set orders: {e}")
            finally:
                bot.print = original_print
                
        except Exception as general_e:
            print(f"Overall turn processing error: {general_e}")
            if hasattr(bot, 'print'):
                bot.print = original_print
