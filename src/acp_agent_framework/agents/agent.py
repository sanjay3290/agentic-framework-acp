"""Primary LLM-backed agent."""
from typing import Any, AsyncGenerator, Callable, Optional, Union
from pydantic import Field
from acp_agent_framework.agents.base import BaseAgent
from acp_agent_framework.backends.acp_backend import AcpBackend
from acp_agent_framework.backends.registry import BackendRegistry
from acp_agent_framework.context import Context
from acp_agent_framework.events import Event

_registry = BackendRegistry()

class Agent(BaseAgent):
    backend: str
    instruction: Union[str, Callable] = Field(exclude=True)
    tools: list[Any] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    output_key: Optional[str] = None
    stream: bool = False
    multi_turn: bool = False
    input_guardrails: list[Any] = Field(default_factory=list)
    output_guardrails: list[Any] = Field(default_factory=list)

    def resolve_instruction(self, ctx: Context) -> str:
        base = self.instruction(ctx) if callable(self.instruction) else self.instruction

        if not self.skills:
            return base

        from acp_agent_framework.skills.loader import SkillLoader
        from acp_agent_framework.skills.skill import Skill

        loaded_skills: list[Skill] = []
        for skill_name in self.skills:
            loaded_skills.append(SkillLoader.load(skill_name, ctx.cwd))

        # Resolve in topological order (dependencies first)
        resolved = SkillLoader.resolve_all(loaded_skills)

        skill_parts = []
        for skill in resolved:
            skill_parts.append(f"## Skill: {skill.name}\n\n{skill.instruction}")

        skills_block = "\n\n---\n\n".join(skill_parts)
        return f"{skills_block}\n\n---\n\n{base}"

    def _get_backend(self) -> AcpBackend:
        config = _registry.get(self.backend)
        return AcpBackend(config)

    async def run(self, ctx: Context) -> AsyncGenerator[Event, None]:
        if self.before_run:
            await self.before_run(ctx)

        mcp_bridge = None
        mcp_servers: list = []

        if self.tools:
            from acp_agent_framework.tools.mcp_bridge import McpBridge
            mcp_bridge = McpBridge(self.tools)
            mcp_bridge.start()
            mcp_servers = [mcp_bridge.get_mcp_config()]

        backend = self._get_backend()
        try:
            await backend.start()
            session_id = await backend.new_session(ctx.cwd, mcp_servers=mcp_servers)
            instruction = self.resolve_instruction(ctx)
            user_input = ctx.get_input() or ""

            # Build prompt with optional conversation history
            parts = []
            if instruction:
                parts.append(instruction)
            if self.multi_turn and ctx.get_history():
                history_lines = []
                for msg in ctx.get_history():
                    role = msg["role"].capitalize()
                    history_lines.append(f"{role}: {msg['content']}")
                parts.append("\n".join(history_lines))
            if user_input:
                parts.append(user_input)
            full_prompt = "\n\n".join(parts)

            # Apply input guardrails
            for guardrail in self.input_guardrails:
                full_prompt = guardrail.validate(full_prompt)

            if self.stream:
                collected = []
                async for chunk in backend.prompt_stream(session_id, full_prompt):
                    collected.append(chunk)
                    yield Event(author=self.name, type="stream_chunk", content=chunk)
                response = "".join(collected)
            else:
                response = await backend.prompt(session_id, full_prompt)

            # Apply output guardrails
            for guardrail in self.output_guardrails:
                response = guardrail.validate(response)

            ctx.set_output(response)
            if self.output_key:
                ctx.state.set(self.output_key, response)
            if self.multi_turn:
                ctx.add_message("user", user_input)
                ctx.add_message("assistant", response)
            yield Event(author=self.name, type="message", content=response)
        finally:
            await backend.stop()
            if mcp_bridge:
                mcp_bridge.stop()

        if self.after_run:
            await self.after_run(ctx)
