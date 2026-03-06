"""Sequential agent - runs sub-agents in order."""
from typing import AsyncGenerator
from pydantic import Field
from acp_agent_framework.agents.base import BaseAgent
from acp_agent_framework.context import Context
from acp_agent_framework.events import Event

class SequentialAgent(BaseAgent):
    agents: list[BaseAgent] = Field(default_factory=list)

    async def run(self, ctx: Context) -> AsyncGenerator[Event, None]:
        if self.before_run:
            await self.before_run(ctx)
        for agent in self.agents:
            async for event in agent.run(ctx):
                yield event
            output = ctx.get_output()
            if output is not None:
                ctx.set_agent_output(agent.name, output)
        if self.after_run:
            await self.after_run(ctx)
