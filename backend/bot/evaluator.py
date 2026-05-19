from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
import json
import os
import re

class AgreementEvaluation(BaseModel):
    agreement_id: int
    could_judge: bool
    score: Optional[int]
    reasoning: str

class BatchEvaluationResponse(BaseModel):
    evaluations: List[AgreementEvaluation]

def evaluate_agreements(game_id: str, game: Any):
    from function_tools.db import get_pending_agreements, update_agreement_status
    
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
    
    # Use Gemma model correctly
    model = ChatGoogleGenerativeAI(model="models/gemma-4-26b-a4b-it", google_api_key=os.getenv("GEMINI_API_KEY"))
    
    batch_size = 5
    for i in range(0, len(pending_agreements), batch_size):
        batch = pending_agreements[i:i + batch_size]
        
        agreements_text = ""
        for agreement in batch:
            agreements_text += f"\n- Agreement ID: {agreement['id']}\n  {agreement['bot_country']} made an agreement with {agreement['agreed_with']}.\n  Details: \"{agreement['agreement']}\"\n"
            
        prompt = f'''
        You are a neutral judge in a game of Diplomacy.
        
        You need to evaluate the following agreements:
        {agreements_text}
        
        The current phase orders are as follows:
        {orders_text}
        
        Based ONLY on the orders above, can you judge if the 'agreed_with' party followed their side of the agreement this turn for each agreement?
        If the agreement is for a future phase or cannot be judged yet, set could_judge to false and score to null.
        If it can be judged, set could_judge to true and provide a score from 0 to 100 representing how well they followed it (e.g. 100 for perfectly followed, 0 for completely broken).
        
        Respond with a JSON object exactly matching this schema:
        {json.dumps(BatchEvaluationResponse.model_json_schema())}
        '''
        
        try:
            response = model.invoke([HumanMessage(content=prompt)])
            raw_text = response.content
            if isinstance(raw_text, list):
                raw_text = "".join(item.get("text", "") if isinstance(item, dict) else str(item) for item in raw_text)
            else:
                raw_text = str(raw_text)
                
            # Grab the last markdown json block 
            blocks = re.findall(r'```(?:json)?(?:\s*)(.*?)(?:\s*)```', raw_text, re.DOTALL)
            if blocks:
                data_dict = json.loads(blocks[-1].strip())
            else:
                match = re.search(r'\{.*\}', raw_text, re.DOTALL)
                if match:
                    data_dict = json.loads(match.group(0))
                else:
                    data_dict = json.loads(raw_text)
                
            if "properties" in data_dict and "evaluations" not in data_dict:
                data_dict = data_dict["properties"]
                
            batch_eval = BatchEvaluationResponse(**data_dict)
            for eval_data in batch_eval.evaluations:
                if eval_data.could_judge and eval_data.score is not None:
                    update_agreement_status(eval_data.agreement_id, eval_data.score)
                    print(f"Evaluated agreement {eval_data.agreement_id}: Score={eval_data.score} ({eval_data.reasoning})")
                else:
                    print(f"Agreement {eval_data.agreement_id} could not be judged yet ({eval_data.reasoning})")
        except Exception as e:
            print(f"Failed to evaluate agreement batch: {e}")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    print("Running evaluator test...")
    test_agreements = [
        {
            'id': 126,
            'bot_country': 'ENGLAND',
            'agreed_with': 'FRANCE',
            'agreement': 'FRA/ENG DMZ in the english channel'
        },
        {
            'id': 127,
            'bot_country': 'GERMANY',
            'agreed_with': 'ENGLAND',
            'agreement': 'I will support your fleet into the English Channel'
        }
    ]
    
    orders_text = "[ENGLAND] F LON - ENG\n[FRANCE] A PAR H\n[GERMANY] F BEL S F LON - ENG"
    
    # Needs to match the actual API model string
    model = ChatGoogleGenerativeAI(model="models/gemma-4-26b-a4b-it", google_api_key=os.getenv("GEMINI_API_KEY"))
    
    agreements_text = ""
    for agreement in test_agreements:
        agreements_text += f"\n- Agreement ID: {agreement['id']}\n  {agreement['bot_country']} made an agreement with {agreement['agreed_with']}.\n  Details: \"{agreement['agreement']}\"\n"
        
    prompt = f'''
    You are a neutral judge in a game of Diplomacy.
    
    You need to evaluate the following agreements:
    {agreements_text}
    
    The current phase orders are as follows:
    {orders_text}
    
    Based ONLY on the orders above, can you judge if the 'agreed_with' party followed their side of the agreement this turn for each agreement?
    If the agreement is for a future phase or cannot be judged yet, set could_judge to false and score to null.
    If it can be judged, set could_judge to true and provide a score from 0 to 100 representing how well they followed it (e.g. 100 for perfectly followed, 0 for completely broken).
    
    Respond with a JSON object exactly matching this schema:
    {json.dumps(BatchEvaluationResponse.model_json_schema())}
    '''
    
    try:
        print("Invoking LLM...")
        response = model.invoke([HumanMessage(content=prompt)])
        raw_text = response.content
        
        if isinstance(raw_text, list):
            raw_text = "".join(item.get("text", "") if isinstance(item, dict) else str(item) for item in raw_text)
        else:
            raw_text = str(raw_text)
            
        print(f"Raw LLM Response:\n{raw_text}")
        
        # Grab the last markdown json block 
        blocks = re.findall(r'```(?:json)?(?:\s*)(.*?)(?:\s*)```', raw_text, re.DOTALL)
        if blocks:
            data_dict = json.loads(blocks[-1].strip())
        else:
            match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if match:
                data_dict = json.loads(match.group(0))
            else:
                data_dict = json.loads(raw_text)
            
        if "properties" in data_dict and "evaluations" not in data_dict:
            data_dict = data_dict["properties"]
            
        batch_eval = BatchEvaluationResponse(**data_dict)
        print(f"\nParsed correctly:")
        for eval_data in batch_eval.evaluations:
            print(f"ID {eval_data.agreement_id}: could_judge={eval_data.could_judge}, score={eval_data.score}, reasoning={eval_data.reasoning}")
    except Exception as e:
        print(f"\nFailed to evaluate: {e}")
