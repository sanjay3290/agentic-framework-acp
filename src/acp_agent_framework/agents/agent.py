"""Primary LLM-backed agent."""
from typing import Any, AsyncGenerator, Callable, Optional, Union
from pydantic import Field
from acp_agent_framework.agents.base import BaseAgent
from acp_agent_framework.backends.acp_backend import AcpBackend
from acp_agent_framework.backends.registry import BackendRegistry
from acp_agent_framework.context import Context
from acp_agent_framework.events import Event

_registry = BackendRegistry()


class _BackendSession:
    def __init__(self, backend, session_id, mcp_bridge=None):
        self.backend = backend
        self.session_id = session_id
        self.mcp_bridge = mcp_bridge
        self.instruction_sent = False

    async def aclose(self):
        try:
            await self.backend.stop()
        finally:
            if self.mcp_bridge:
                self.mcp_bridge.stop()


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

        key = f"backend:{self.name}"
        async with ctx.resource_lock(key):
            sess = ctx.get_resource(key)

            if sess is not None and not sess.backend.is_running:
                await sess.aclose()
                ctx.pop_resource(key)
                sess = None

            if sess is None:
                mcp_bridge = None
                mcp_servers: list = []
                backend = None
                try:
                    if self.tools:
                        from acp_agent_framework.tools.mcp_bridge import McpBridge
                        mcp_bridge = McpBridge(self.tools)
                        mcp_bridge.start()
                        mcp_servers = [mcp_bridge.get_mcp_config()]

                    backend = self._get_backend()
                    await backend.start()
                    session_id = await backend.new_session(ctx.cwd, mcp_servers=mcp_servers)
                    sess = _BackendSession(backend, session_id, mcp_bridge)
                    ctx.set_resource(key, sess)
                except Exception:
                    # Clean up anything that was started (F1).
                    # Bridge cleanup must run even if backend.stop() raises.
                    try:
                        if backend is not None:
                            await backend.stop()
                    finally:
                        if mcp_bridge is not None:
                            mcp_bridge.stop()
                    raise

            user_input = ctx.get_input() or ""

            # Build prompt: instruction + history only on first use of this backend
            parts = []
            if not sess.instruction_sent:
                instruction = self.resolve_instruction(ctx)
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

            try:
                if self.stream:
                    collected = []
                    async for chunk in sess.backend.prompt_stream(sess.session_id, full_prompt):
                        collected.append(chunk)
                        yield Event(author=self.name, type="stream_chunk", content=chunk)
                    response = "".join(collected)
                else:
                    response = await sess.backend.prompt(sess.session_id, full_prompt)
            except Exception:
                await sess.aclose()
                ctx.pop_resource(key)
                raise

            sess.instruction_sent = True

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

        if self.after_run:
            await self.after_run(ctx)
