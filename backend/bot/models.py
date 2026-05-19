from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional

class OrderItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    location: str = Field(description="The map location (e.g., 'PAR')")
    order: str = Field(description="The full order string (e.g., 'A PAR - BUR')")

class MessageItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    recipient: str = Field(description="The power to send the message to (e.g., 'ENGLAND', 'FRANCE', or 'GLOBAL')")
    message: str = Field(description="The content of the message")

class AgreementItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    agreed_with: str = Field(description="The country the agreement is made with (e.g., 'ENGLAND')")
    agreement: str = Field(description="A clear, actionable summary of the agreement.")

class BotTurnResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reasoning: str = Field(description="Strategic justification. Explain your plan to reach 18 centers.")
    messages: Optional[List[MessageItem]] = Field(default=None, description="Optional list of messages to send to other powers. Try to rely LESS on messages. Stay mysterious.")

class BotReactionResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reasoning: str = Field(description="Strategic justification for the reaction.")
    messages: Optional[List[MessageItem]] = Field(default=None, description="Optional list of messages to send in reply. Leave an empty array if a reply is not strictly necessary.")
    agreements: Optional[List[AgreementItem]] = Field(default=None, description="Only include if you are ACCEPTING a proposed agreement in this exact message round.")

class BotOrderResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reasoning: str = Field(description="Strategic justification for your final orders. Detail how you will betray or uphold your agreements.")
    orders: List[OrderItem] = Field(description="List of final orders for each location.")

