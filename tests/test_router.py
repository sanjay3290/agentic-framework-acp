import pytest
from acp_agent_framework.agents.agent import Agent
from acp_agent_framework.agents.router import Route, RouterAgent
from acp_agent_framework.context import Context
from acp_agent_framework.events import Event

def _mock_agent(name, output):
    agent = Agent(name=name, backend="claude", instruction="test")
    async def fake_run(ctx):
        ctx.set_output(output)
        yield Event(author=name, type="message", content=output)
    object.__setattr__(agent, "run", fake_run)
    return agent

@pytest.mark.asyncio
async def test_router_keyword_matching():
    code_agent = _mock_agent("coder", "code output")
    write_agent = _mock_agent("writer", "write output")
    router = RouterAgent(
        name="router",
        routes=[
            Route(keywords=["code", "fix", "debug"], agent=code_agent),
            Route(keywords=["write", "draft", "essay"], agent=write_agent),
        ],
    )
    ctx = Context(session_id="s1", cwd="/tmp")
    ctx.set_input("Please fix this bug")
    events = []
    async for event in router.run(ctx):
        events.append(event)
    assert events[0].author == "coder"

@pytest.mark.asyncio
async def test_router_default_agent():
    code_agent = _mock_agent("coder", "code output")
    default_agent = _mock_agent("default", "default output")
    router = RouterAgent(
        name="router",
        routes=[Route(keywords=["code"], agent=code_agent)],
        default_agent=default_agent,
    )
    ctx = Context(session_id="s1", cwd="/tmp")
    ctx.set_input("Tell me a joke")
    events = []
    async for event in router.run(ctx):
        events.append(event)
    assert events[0].author == "default"

@pytest.mark.asyncio
async def test_router_no_match_no_default():
    code_agent = _mock_agent("coder", "code output")
    router = RouterAgent(name="router", routes=[Route(keywords=["code"], agent=code_agent)])
    ctx = Context(session_id="s1", cwd="/tmp")
    ctx.set_input("Tell me a joke")
    events = []
    async for event in router.run(ctx):
        events.append(event)
    assert len(events) == 1
    assert "no matching route" in events[0].content.lower()
