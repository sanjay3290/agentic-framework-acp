import pytest
from acp_agent_framework.agents.tool_agent import ToolAgent
from acp_agent_framework.tools.function_tool import FunctionTool
from acp_agent_framework.context import Context


def multiply(a: int, b: int) -> int:
    """Multiply two numbers."""
    return a * b


async def fetch_data(url: str) -> str:
    """Fetch data from a URL."""
    return f"Data from {url}"


@pytest.mark.asyncio
async def test_tool_agent_runs_execute():
    tool = FunctionTool(multiply)

    async def my_execute(ctx, tools):
        result = tools["multiply"].run({"a": 3, "b": 7})
        return f"Result: {result}"

    agent = ToolAgent(name="calc", tools=[tool], execute=my_execute)
    ctx = Context(session_id="s1", cwd="/tmp")
    events = []
    async for event in agent.run(ctx):
        events.append(event)
    assert len(events) == 1
    assert events[0].content == "Result: 21"
    assert events[0].type == "tool_result"
    assert ctx.get_output() == "Result: 21"


@pytest.mark.asyncio
async def test_tool_agent_with_output_key():
    tool = FunctionTool(multiply)

    async def my_execute(ctx, tools):
        return tools["multiply"].run({"a": 5, "b": 5})

    agent = ToolAgent(name="calc", tools=[tool], execute=my_execute, output_key="answer")
    ctx = Context(session_id="s1", cwd="/tmp")
    async for _ in agent.run(ctx):
        pass
    assert ctx.state.get("answer") == "25"


@pytest.mark.asyncio
async def test_tool_agent_multiple_tools():
    tool1 = FunctionTool(multiply)
    tool2 = FunctionTool(fetch_data)

    async def my_execute(ctx, tools):
        product = tools["multiply"].run({"a": 2, "b": 3})
        data = await tools["fetch_data"].arun({"url": "https://example.com"})
        return f"{product} | {data}"

    agent = ToolAgent(name="multi", tools=[tool1, tool2], execute=my_execute)
    ctx = Context(session_id="s1", cwd="/tmp")
    events = []
    async for event in agent.run(ctx):
        events.append(event)
    assert "6" in events[0].content
    assert "Data from https://example.com" in events[0].content


@pytest.mark.asyncio
async def test_tool_agent_in_sequential():
    from acp_agent_framework.agents.sequential import SequentialAgent
    from acp_agent_framework.agents.base import BaseAgent
    from acp_agent_framework.events import Event

    tool = FunctionTool(multiply)

    async def calc_execute(ctx, tools):
        return tools["multiply"].run({"a": 4, "b": 10})

    tool_agent = ToolAgent(name="calc", tools=[tool], execute=calc_execute, output_key="calc_result")

    class MockSummary(BaseAgent):
        name: str = "summary"
        async def run(self, ctx):
            val = ctx.state.get("calc_result", "none")
            ctx.set_output(f"Summary: {val}")
            yield Event(author=self.name, type="message", content=f"Summary: {val}")

    seq = SequentialAgent(name="pipeline", agents=[tool_agent, MockSummary(name="summary")])
    ctx = Context(session_id="s1", cwd="/tmp")
    events = []
    async for event in seq.run(ctx):
        events.append(event)
    assert len(events) == 2
    assert events[0].content == "40"
    assert events[1].content == "Summary: 40"
