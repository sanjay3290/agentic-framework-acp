"""Router agent - routes prompts to sub-agents based on rules."""
from typing import AsyncGenerator, Optional
from pydantic import BaseModel, Field
from acp_agent_framework.agents.base import BaseAgent
from acp_agent_framework.context import Context
from acp_agent_framework.events import Event

class Route(BaseModel):
    model_config = {"arbitrary_types_allowed": True}
    keywords: list[str]
    agent: BaseAgent

class RouterAgent(BaseAgent):
    routes: list[Route] = Field(default_factory=list)
    default_agent: Optional[BaseAgent] = None

    def _find_route(self, text: str) -> Optional[BaseAgent]:
        text_lower = text.lower()
        for route in self.routes:
            if any(kw.lower() in text_lower for kw in route.keywords):
                return route.agent
        return self.default_agent

    async def run(self, ctx: Context) -> AsyncGenerator[Event, None]:
        if self.before_run:
            await self.before_run(ctx)
        user_input = ctx.get_input() or ""
        target = self._find_route(user_input)
        if target is None:
            yield Event(author=self.name, type="message", content="No matching route found for input.")
            return
        async for event in target.run(ctx):
            yield event
        if self.after_run:
            await self.after_run(ctx)
