import pytest
from acp_agent_framework.agents.agent import Agent
from acp_agent_framework.agents.sequential import SequentialAgent
from acp_agent_framework.context import Context
from acp_agent_framework.events import Event

def _mock_agent(name, output):
    agent = Agent(name=name, backend="claude", instruction="test")
    async def fake_run(ctx):
        ctx.set_output(output)
        ctx.set_agent_output(name, output)
        yield Event(author=name, type="message", content=output)
    object.__setattr__(agent, "run", fake_run)
    return agent

@pytest.mark.asyncio
async def test_sequential_runs_in_order():
    a1 = _mock_agent("first", "output-1")
    a2 = _mock_agent("second", "output-2")
    seq = SequentialAgent(name="pipeline", agents=[a1, a2])
    ctx = Context(session_id="s1", cwd="/tmp")
    ctx.set_input("start")
    events = []
    async for event in seq.run(ctx):
        events.append(event)
    assert len(events) == 2
    assert events[0].author == "first"
    assert events[1].author == "second"
    assert ctx.get_output() == "output-2"

@pytest.mark.asyncio
async def test_sequential_passes_output_to_next():
    async def check_run(ctx):
        prev = ctx.get_agent_output("first")
        assert prev == "output-1"
        ctx.set_output("combined")
        yield Event(author="second", type="message", content="combined")
    a1 = _mock_agent("first", "output-1")
    a2 = Agent(name="second", backend="claude", instruction="test")
    object.__setattr__(a2, "run", check_run)
    seq = SequentialAgent(name="pipeline", agents=[a1, a2])
    ctx = Context(session_id="s1", cwd="/tmp")
    events = []
    async for event in seq.run(ctx):
        events.append(event)
    assert ctx.get_output() == "combined"

@pytest.mark.asyncio
async def test_sequential_empty_agents():
    seq = SequentialAgent(name="empty", agents=[])
    ctx = Context(session_id="s1", cwd="/tmp")
    events = []
    async for event in seq.run(ctx):
        events.append(event)
    assert events == []
