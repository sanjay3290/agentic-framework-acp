"""ACP Agent Framework - Build custom ACP agents using existing AI subscriptions."""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("acp-agent-framework")
except PackageNotFoundError:
    __version__ = "0.0.0.dev0"

from acp_agent_framework.agents import Agent, BaseAgent, Route, RouterAgent, SequentialAgent, ToolAgent
from acp_agent_framework.backends import BackendConfig, BackendRegistry
from acp_agent_framework.context import Context
from acp_agent_framework.events import Event, EventActions
from acp_agent_framework.skills import Skill, SkillLoader
from acp_agent_framework.state import State
from acp_agent_framework.tools import AgentTool, BaseTool, FunctionTool, McpBridge
from acp_agent_framework.guardrails import Guardrail, GuardrailError
from acp_agent_framework.observability import AgentLogger, get_logger
from acp_agent_framework.server.serve import serve

__all__ = [
    "Agent",
    "AgentLogger",
    "BaseAgent",
    "BackendConfig",
    "BackendRegistry",
    "Context",
    "Event",
    "EventActions",
    "AgentTool",
    "Guardrail",
    "GuardrailError",
    "FunctionTool",
    "BaseTool",
    "McpBridge",
    "Route",
    "RouterAgent",
    "SequentialAgent",
    "Skill",
    "SkillLoader",
    "State",
    "ToolAgent",
    "get_logger",
    "serve",
    "__version__",
]
