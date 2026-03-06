import pytest
from acp_agent_framework.agents.base import BaseAgent
from acp_agent_framework.agents.agent import Agent
from acp_agent_framework.context import Context

def test_agent_creation():
    agent = Agent(name="helper", backend="claude", instruction="You are a helpful assistant.")
    assert agent.name == "helper"
    assert agent.backend == "claude"
    assert agent.instruction == "You are a helpful assistant."
    assert agent.tools == []
    assert agent.sub_agents == []

def test_agent_description():
    agent = Agent(name="helper", description="A helpful coding assistant", backend="claude", instruction="Help with code.")
    assert agent.description == "A helpful coding assistant"

def test_agent_with_dynamic_instruction():
    def make_instruction(ctx: Context) -> str:
        return f"You are helping in {ctx.cwd}"
    agent = Agent(name="helper", backend="claude", instruction=make_instruction)
    ctx = Context(session_id="s1", cwd="/my/project")
    resolved = agent.resolve_instruction(ctx)
    assert resolved == "You are helping in /my/project"

def test_agent_with_string_instruction():
    agent = Agent(name="helper", backend="claude", instruction="Be helpful.")
    ctx = Context(session_id="s1", cwd="/tmp")
    resolved = agent.resolve_instruction(ctx)
    assert resolved == "Be helpful."

def test_agent_name_validation():
    with pytest.raises(ValueError):
        Agent(name="", backend="claude", instruction="test")

def test_base_agent_is_abstract():
    with pytest.raises(TypeError):
        BaseAgent(name="test")
