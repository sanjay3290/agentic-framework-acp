"""ToolAgent - executes tools directly without an LLM backend."""
from typing import Any, AsyncGenerator, Callable, Optional
from pydantic import Field
from acp_agent_framework.agents.base import BaseAgent
from acp_agent_framework.context import Context
from acp_agent_framework.events import Event


class ToolAgent(BaseAgent):
    """Agent that executes tools via a user-defined execute function.

    No LLM backend needed. The user provides an async execute function
    that receives the context and a dict of tools, runs them directly,
    and returns a string result.
    """
    tools: list[Any] = Field(default_factory=list)
    execute: Callable = Field(exclude=True)
    output_key: Optional[str] = None

    async def run(self, ctx: Context) -> AsyncGenerator[Event, None]:
        if self.before_run:
            await self.before_run(ctx)

        tools_dict = {tool.name: tool for tool in self.tools}
        result = await self.execute(ctx, tools_dict)
        result_str = str(result) if result is not None else ""

        ctx.set_output(result_str)
        if self.output_key:
            ctx.state.set(self.output_key, result_str)

        yield Event(author=self.name, type="tool_result", content=result_str)

        if self.after_run:
            await self.after_run(ctx)
