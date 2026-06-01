from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from bot.bot import invoke_with_retry, get_model
from langchain_core.messages import HumanMessage
import json
import os
import re

class AgreementEvaluation(BaseModel):
    agreement_id: int = Field(description="The ID of the agreement being evaluated.")
    reasoning: str = Field(description="Chain of thought reasoning. Analyze text of agreement vs exact orders. STRATEGIC CONTEXT: Evaluate if actions taken against third parties contradict the spirit of the alliance (e.g. attacking an ally's other ally).")
    could_judge: bool = Field(description="Set to true if you can conclusively judge based ONLY on provided orders. INCONCLUSIVE STATE: If an order does not involve the agreed-upon territory/goal, or if they move closer to a long-term goal but don't achieve it yet, MUST set to false (neutral/positional).")
    score: Optional[int] = Field(description="If could_judge is true, provide a score from 0 to 100 (100 = followed exactly, 0 = deliberately broken/attacked). STRICT NOTATION: 'S' = Support, '-' = Move/Attack. If bot promised to 'Support' but issued a 'Move' order instead, this is a 'Fake Support' betrayal and MUST be scored 0.")

class BetrayalAnalysis(BaseModel):
    reasoning: str = Field(description="Chain of thought reasoning. Analyze the map and orders for any clear betrayals, surprise invasions, or unprovoked attacks between powers previously at peace.")
    is_betrayal: bool = Field(description="Only report GENUINE betrayals that are clear from the orders.")
    betrayer: str = Field(description="The power committing the betrayal.")
    victim: str = Field(description="The power being betrayed.")
    description: str = Field(description="Describe the betrayal. PREEMPTIVE ATTACKS: Look closely for aggressive moves into another power's home centers, critical borders, or agreed DMZs (like English Channel) without warning.")
    trust_score: int = Field(description="0 to 100, where 0 is a massive unprovoked backstab.")

class JointEvaluationResponse(BaseModel):
    evaluations: List[AgreementEvaluation]
    betrayals: List[BetrayalAnalysis]

def evaluate_agreements(game_id: str, game: Any):
    """
    Evaluates both formal agreements (press) and map betrayals (moves) in a single LLM call.
    """
    from function_tools.db import get_pending_agreements, update_agreement_status, add_agreement, get_connection
    
    pending_agreements = get_pending_agreements(game_id)
    
    # Gather orders for the current phase across all powers
    all_orders = []
    for power in game.powers:
        orders = game.get_orders(power)
        if orders:
            all_orders.extend([f"[{power}] {o}" for o in orders])
            
    if not all_orders:
        return
        
    phase_str = game.get_current_phase() if hasattr(game, "get_current_phase") else "Unknown Phase"
    phase = phase_str.name if hasattr(phase_str, "name") else str(phase_str)
    orders_text = "\n".join(all_orders)
    
    # We use Gemini for the complex joint task
    model = get_model()
    
    agreements_text = "NONE"
    if pending_agreements:
        agreements_text = ""
        for agreement in pending_agreements:
            agreements_text += f"\n- Agreement ID: {agreement['id']}\n  {agreement['bot_country']} made an agreement with {agreement['agreed_with']}.\n  Details: \"{agreement['agreement']}\"\n"
            
    prompt = f'''
        You are a neutral judge in a game of Diplomacy. The current phase is {phase}.
        
        PART 1: Evaluate Existing Agreements
        Existing Agreements:
        {agreements_text}
        
        Current phase orders:
        {orders_text}
        
        Respond with a JSON object exactly matching this schema:
        {json.dumps(JointEvaluationResponse.model_json_schema())}
        '''    
    try:
        response = model.with_structured_output(JointEvaluationResponse).invoke([HumanMessage(content=prompt)])
        
        # 1. Process Evaluations
        for eval_data in response.evaluations:
            if eval_data.could_judge and eval_data.score is not None:
                update_agreement_status(eval_data.agreement_id, eval_data.score)
                print(f"[Judge] Evaluated agreement {eval_data.agreement_id}: Score={eval_data.score} ({eval_data.reasoning})")
            else:
                print(f"[Judge] Agreement {eval_data.agreement_id} could not be judged yet ({eval_data.reasoning})")
        
        # 2. Process Map Betrayals (Unrecorded agreements)
        for b in response.betrayals:
            if b.is_betrayal:
                desc = f"[MAP BETRAYAL] {b.description}"
                # Log it as a new agreement that is already broken
                add_agreement(game_id, b.victim, b.betrayer, desc, phase)
                
                # Update the score immediately
                conn = get_connection()
                try:
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE trust_ledger SET followed = %s 
                            WHERE game_id=%s AND bot_country=%s AND agreed_with=%s AND agreement=%s
                        """, (b.trust_score, game_id, b.victim, b.betrayer, desc))
                    conn.commit()
                finally:
                    conn.close()
                print(f"[Judge] Logged Map Betrayal: {b.betrayer} stabbed {b.victim}")
    except Exception as e:
        print(f"Failed to evaluate turn: {e}")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    print("Combined evaluator script available.")
