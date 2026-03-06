"""Event system for agent communication."""
import time
import uuid
from typing import Any, Optional
from pydantic import BaseModel, Field

class EventActions(BaseModel):
    state_delta: dict[str, Any] = Field(default_factory=dict)
    transfer_to_agent: Optional[str] = None
    escalate: Optional[bool] = None

class Event(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    author: str
    type: str
    content: Any
    timestamp: float = Field(default_factory=time.time)
    actions: Optional[EventActions] = None
