"""ACP server that wraps a framework agent as an ACP-compatible agent."""
import uuid
from typing import Any, Optional
import acp
from acp import helpers
from acp_agent_framework.agents.base import BaseAgent
from acp_agent_framework.context import Context


class FrameworkAgent:
    def __init__(self, agent: BaseAgent) -> None:
        self._agent = agent
        self._sessions: dict[str, Context] = {}
        self._connection: Optional[Any] = None

    def set_connection(self, conn: Any) -> None:
        self._connection = conn

    def on_connect(self, conn: Any) -> None:
        """Called by ACP when an agent connection is established."""
        self._connection = conn

    async def initialize(self, protocol_version: int, client_capabilities=None, client_info=None, **kwargs):
        return acp.InitializeResponse(
            protocol_version=acp.PROTOCOL_VERSION,
            agent_capabilities=acp.schema.AgentCapabilities(
                prompt_capabilities=acp.schema.PromptCapabilities(image=False, embedded_context=False),
            ),
            agent_info=acp.schema.Implementation(name=self._agent.name, version="0.1.0"),
            auth_methods=[],
        )

    async def authenticate(self, method_id: str, **kwargs):
        return acp.AuthenticateResponse()

    async def new_session(self, cwd: str, mcp_servers=None, **kwargs):
        session_id = str(uuid.uuid4())
        ctx = Context(session_id=session_id, cwd=cwd)
        self._sessions[session_id] = ctx
        return acp.NewSessionResponse(session_id=session_id)

    async def load_session(self, cwd: str, session_id: str, mcp_servers=None, **kwargs):
        if session_id not in self._sessions:
            raise acp.RequestError(-32002, f"Session not found: {session_id}")
        return acp.LoadSessionResponse()

    async def list_sessions(self, cursor=None, cwd=None, **kwargs):
        sessions = []
        for sid, ctx in self._sessions.items():
            if cwd and ctx.cwd != cwd:
                continue
            sessions.append(acp.schema.SessionInfo(session_id=sid, cwd=ctx.cwd))
        return acp.schema.ListSessionsResponse(sessions=sessions)

    async def set_session_mode(self, mode_id, session_id, **kwargs):
        return acp.SetSessionModeResponse()

    async def set_session_model(self, model_id, session_id, **kwargs):
        return acp.SetSessionModelResponse()

    async def set_config_option(self, config_id, session_id, value, **kwargs):
        return acp.SetSessionConfigOptionResponse()

    async def prompt(self, prompt, session_id, **kwargs):
        ctx = self._sessions.get(session_id)
        if not ctx:
            raise acp.RequestError(-32002, f"Session not found: {session_id}")
        text_parts = []
        for block in prompt:
            if hasattr(block, "text"):
                text_parts.append(block.text)
        user_input = "\n".join(text_parts)
        ctx.set_input(user_input)
        async for event in self._agent.run(ctx):
            if self._connection and event.type == "message":
                update = helpers.update_agent_message_text(str(event.content))
                await self._connection.send_notification(
                    helpers.session_notification(session_id=session_id, update=update)
                )
        return acp.PromptResponse(stop_reason="end_turn")
