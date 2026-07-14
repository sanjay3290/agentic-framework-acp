import pytest

from acp_agent_framework.context import Context
from acp_agent_framework.state import State

def test_context_creation():
    ctx = Context(session_id="sess-1", cwd="/tmp/project")
    assert ctx.session_id == "sess-1"
    assert ctx.cwd == "/tmp/project"
    assert isinstance(ctx.state, State)

def test_context_with_existing_state():
    state = State(initial={"key": "value"})
    ctx = Context(session_id="sess-1", cwd="/tmp", state=state)
    assert ctx.state.get("key") == "value"

def test_context_input_output():
    ctx = Context(session_id="sess-1", cwd="/tmp")
    ctx.set_input("Hello")
    assert ctx.get_input() == "Hello"
    ctx.set_output("World")
    assert ctx.get_output() == "World"

def test_context_agent_outputs():
    ctx = Context(session_id="sess-1", cwd="/tmp")
    ctx.set_agent_output("researcher", "found 3 results")
    ctx.set_agent_output("writer", "summary written")
    assert ctx.get_agent_output("researcher") == "found 3 results"
    assert ctx.get_agent_output("writer") == "summary written"
    assert ctx.get_agent_output("unknown") is None


def test_context_history():
    ctx = Context(session_id="s1", cwd="/tmp")
    assert ctx.get_history() == []
    ctx.add_message("user", "Hello")
    ctx.add_message("assistant", "Hi!")
    assert len(ctx.get_history()) == 2
    assert ctx.get_history()[0] == {"role": "user", "content": "Hello"}
    assert ctx.get_history()[1] == {"role": "assistant", "content": "Hi!"}


def test_context_clear_history():
    ctx = Context(session_id="s1", cwd="/tmp")
    ctx.add_message("user", "Hello")
    ctx.clear_history()
    assert ctx.get_history() == []


@pytest.mark.asyncio
async def test_context_close_closes_all_and_reraises_first_error():
    """F6: close() always clears resources; healthy resources close even if one fails."""

    class FailingResource:
        def __init__(self):
            self.closed = False

        async def aclose(self):
            self.closed = True
            raise RuntimeError("aclose A failed")

    class HealthyResource:
        def __init__(self):
            self.closed = False

        async def aclose(self):
            self.closed = True

    ctx = Context(session_id="s1", cwd="/tmp")
    a = FailingResource()
    b = HealthyResource()
    ctx.set_resource("a", a)
    ctx.set_resource("b", b)

    with pytest.raises(RuntimeError, match="aclose A failed"):
        await ctx.close()

    assert a.closed is True
    assert b.closed is True
    assert ctx._resources == {}
    assert ctx._resource_locks == {}
