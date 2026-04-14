from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
import json
import os
import re

class AgreementEvaluation(BaseModel):
    followed: bool
    reasoning: str

def evaluate_agreements(game_id: str, game: Any):
    from bot.db import get_pending_agreements, update_agreement_status
    
    pending_agreements = get_pending_agreements(game_id)
    if not pending_agreements:
        return
        
    # Gather orders for the current phase across all powers
    all_orders = []
    for power in game.powers:
        orders = game.get_orders(power)
        if orders:
            all_orders.extend([f"[{power}] {o}" for o in orders])
            
    if not all_orders:
        return
        
    orders_text = "\n".join(all_orders)
    
    # Use Gemma model
    model = ChatGoogleGenerativeAI(model="models/gemma-3-12b-it", google_api_key=os.getenv("GEMINI_API_KEY"))
    
    for agreement in pending_agreements:
        prompt = f"""
        You are a neutral judge in a game of Diplomacy.
        
        Agreement: {agreement['bot_country']} made an agreement with {agreement['agreed_with']}.
        The agreement details: "{agreement['agreement']}"
        
        The current phase orders are as follows:
        {orders_text}
        
        Based ONLY on the orders above, did {agreement['agreed_with']} follow their side of the agreement? 
        If the agreement required {agreement['agreed_with']} to do something (or not do something) and their orders reflect that, they followed it.
        If their orders contradict the agreement, they broke it.
        If it's impossible to tell from just these orders, or the agreement was for a future phase, assume they followed it (true) or that it is not yet broken.
        
        Respond with a JSON object exactly matching this schema:
        {AgreementEvaluation.model_json_schema()}
        """
        
        try:
            response = model.invoke([HumanMessage(content=prompt)])
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
                
            eval_data = AgreementEvaluation(**data_dict)
            update_agreement_status(agreement['id'], eval_data.followed)
            print(f"Evaluated agreement {agreement['id']}: Followed={eval_data.followed} ({eval_data.reasoning})")
        except Exception as e:
            print(f"Failed to evaluate agreement {agreement['id']}: {e}")
