"""Base agent class - all agents extend this."""
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Callable, Optional
from pydantic import BaseModel, Field, field_validator
from acp_agent_framework.context import Context
from acp_agent_framework.events import Event

class BaseAgent(ABC, BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    name: str
    description: str = ""
    sub_agents: list[Any] = Field(default_factory=list)
    before_run: Optional[Callable] = Field(default=None, exclude=True)
    after_run: Optional[Callable] = Field(default=None, exclude=True)

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Agent name must not be empty")
        return v

    @abstractmethod
    async def run(self, ctx: Context) -> AsyncGenerator[Event, None]:
        yield  # type: ignore
