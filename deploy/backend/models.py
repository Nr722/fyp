from pydantic import BaseModel, Field, ConfigDict
from typing import List

class OrderItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    location: str = Field(description="The map location (e.g., 'PAR')")
    order: str = Field(description="The full order string (e.g., 'A PAR - BUR')")

class BotTurnResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reasoning: str = Field(description="Strategic justification.")
    # We change from Dict to List to avoid the 'additionalProperties' error
    orders: List[OrderItem] = Field(description="List of orders for each location.")