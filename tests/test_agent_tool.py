import pytest
from acp_agent_framework.agents.base import BaseAgent
from acp_agent_framework.tools.agent_tool import AgentTool
from acp_agent_framework.context import Context
from acp_agent_framework.events import Event


class EchoAgent(BaseAgent):
    name: str = "echo"
    description: str = "Echoes input back"

    async def run(self, ctx):
        text = ctx.get_input() or ""
        ctx.set_output(f"Echo: {text}")
        yield Event(author=self.name, type="message", content=f"Echo: {text}")


class UpperAgent(BaseAgent):
    name: str = "upper"
    description: str = "Uppercases input"

    async def run(self, ctx):
        text = ctx.get_input() or ""
        result = text.upper()
        ctx.set_output(result)
        yield Event(author=self.name, type="message", content=result)


def test_agent_tool_creation():
    agent = EchoAgent(name="echo")
    tool = AgentTool(agent)
    assert tool.name == "echo"
    assert tool.description == "Echoes input back"


def test_agent_tool_schema():
    agent = EchoAgent(name="echo")
    tool = AgentTool(agent)
    schema = tool.get_schema()
    assert schema["name"] == "echo"
    assert "prompt" in schema["parameters"]


def test_agent_tool_rejects_non_agent():
    with pytest.raises(TypeError, match="Expected BaseAgent"):
        AgentTool("not an agent")


@pytest.mark.asyncio
async def test_agent_tool_arun():
    agent = EchoAgent(name="echo")
    tool = AgentTool(agent)
    result = await tool.arun({"prompt": "hello"})
    assert result == "Echo: hello"


@pytest.mark.asyncio
async def test_agent_tool_arun_with_input_key():
    agent = EchoAgent(name="echo")
    tool = AgentTool(agent)
    result = await tool.arun({"input": "world"})
    assert result == "Echo: world"


@pytest.mark.asyncio
async def test_agent_tool_in_tool_agent():
    from acp_agent_framework.agents.tool_agent import ToolAgent

    echo = EchoAgent(name="echo")
    upper = UpperAgent(name="upper")
    echo_tool = AgentTool(echo)
    upper_tool = AgentTool(upper)

    async def orchestrate(ctx, tools):
        echo_result = await tools["echo"].arun({"prompt": "hello"})
        upper_result = await tools["upper"].arun({"prompt": echo_result})
        return upper_result

    agent = ToolAgent(
        name="orchestrator",
        tools=[echo_tool, upper_tool],
        execute=orchestrate,
    )
    ctx = Context(session_id="s1", cwd="/tmp")
    ctx.set_input("test")
    events = []
    async for event in agent.run(ctx):
        events.append(event)
    assert len(events) == 1
    assert events[0].content == "ECHO: HELLO"
