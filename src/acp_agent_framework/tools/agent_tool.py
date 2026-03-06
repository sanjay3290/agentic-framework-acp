"""Wrap a BaseAgent as a tool for agent-to-agent communication."""
import asyncio
from typing import Any
from acp_agent_framework.tools.base import BaseTool
from acp_agent_framework.context import Context


class AgentTool(BaseTool):
    """Wraps a BaseAgent so it can be invoked as a tool by another agent."""

    def __init__(self, agent: Any, cwd: str = ".") -> None:
        from acp_agent_framework.agents.base import BaseAgent
        if not isinstance(agent, BaseAgent):
            raise TypeError(f"Expected BaseAgent, got {type(agent).__name__}")
        self._agent = agent
        self._cwd = cwd
        self.name = agent.name
        self.description = agent.description or f"Delegate to {agent.name} agent"

    def run(self, args: dict[str, Any]) -> Any:
        """Run the wrapped agent synchronously (blocks until complete)."""
        try:
            asyncio.get_running_loop()
            raise RuntimeError(
                "AgentTool.run() cannot be called from an async context. Use await arun() instead."
            )
        except RuntimeError as e:
            if "no running event loop" not in str(e):
                raise
        return asyncio.run(self._run_agent(args))

    async def arun(self, args: dict[str, Any]) -> Any:
        """Run the wrapped agent asynchronously."""
        return await self._run_agent(args)

    async def _run_agent(self, args: dict[str, Any]) -> str:
        prompt = args.get("prompt", args.get("input", ""))
        ctx = Context(session_id=f"agent-tool-{self.name}", cwd=self._cwd)
        ctx.set_input(str(prompt))
        results = []
        async for event in self._agent.run(ctx):
            if event.type == "message":
                results.append(str(event.content))
        return "\n".join(results) if results else ctx.get_output() or ""

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "prompt": {"type": "str", "description": "Input prompt for the agent"},
            },
        }
