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

class BotTurnResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reasoning: str = Field(description="Strategic justification.")
    # We change from Dict to List to avoid the 'additionalProperties' error
    orders: List[OrderItem] = Field(description="List of orders for each location.")
    messages: Optional[List[MessageItem]] = Field(default=None, description="Optional list of messages to send to other powers.")

class BotReactionResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reasoning: str = Field(description="Strategic justification for the reaction.")
    messages: Optional[List[MessageItem]] = Field(default=None, description="Optional list of messages to send in reply.")
    orders: Optional[List[OrderItem]] = Field(default=None, description="Optional list of updated orders. Only include if you want to change your current orders.")
