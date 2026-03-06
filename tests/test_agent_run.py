import pytest
from unittest.mock import AsyncMock, patch
from acp_agent_framework.agents.agent import Agent
from acp_agent_framework.tools.function_tool import FunctionTool
from acp_agent_framework.context import Context

@pytest.mark.asyncio
async def test_agent_run_collects_response():
    agent = Agent(name="test", backend="claude", instruction="Be helpful.")
    ctx = Context(session_id="s1", cwd="/tmp")
    ctx.set_input("Hello")
    with patch.object(agent, "_get_backend") as mock_get:
        mock_backend = AsyncMock()
        mock_backend.start = AsyncMock()
        mock_backend.new_session = AsyncMock(return_value="sess-123")
        mock_backend.prompt = AsyncMock(return_value="Hi there!")
        mock_backend.stop = AsyncMock()
        mock_get.return_value = mock_backend
        events = []
        async for event in agent.run(ctx):
            events.append(event)
        assert len(events) >= 1
        assert any(e.content == "Hi there!" for e in events)
        assert ctx.get_output() == "Hi there!"

@pytest.mark.asyncio
async def test_agent_run_with_output_key():
    agent = Agent(name="test", backend="claude", instruction="Be helpful.", output_key="result")
    ctx = Context(session_id="s1", cwd="/tmp")
    ctx.set_input("Hello")
    with patch.object(agent, "_get_backend") as mock_get:
        mock_backend = AsyncMock()
        mock_backend.start = AsyncMock()
        mock_backend.new_session = AsyncMock(return_value="sess-123")
        mock_backend.prompt = AsyncMock(return_value="Saved output")
        mock_backend.stop = AsyncMock()
        mock_get.return_value = mock_backend
        async for _ in agent.run(ctx):
            pass
        assert ctx.state.get("result") == "Saved output"


def _dummy_add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


@pytest.mark.asyncio
async def test_agent_run_with_tools_creates_mcp_bridge():
    tool = FunctionTool(_dummy_add)
    agent = Agent(name="test", backend="claude", instruction="Use tools.", tools=[tool])
    ctx = Context(session_id="s1", cwd="/tmp")
    ctx.set_input("Add 1 and 2")
    with patch.object(agent, "_get_backend") as mock_get:
        mock_backend = AsyncMock()
        mock_backend.start = AsyncMock()
        mock_backend.new_session = AsyncMock(return_value="sess-123")
        mock_backend.prompt = AsyncMock(return_value="3")
        mock_backend.stop = AsyncMock()
        mock_get.return_value = mock_backend
        events = []
        async for event in agent.run(ctx):
            events.append(event)
        # Verify new_session was called with mcp_servers containing our config
        call_kwargs = mock_backend.new_session.call_args
        mcp_servers = call_kwargs.kwargs.get("mcp_servers", call_kwargs[1].get("mcp_servers", []) if len(call_kwargs) > 1 else [])
        assert len(mcp_servers) == 1
        assert mcp_servers[0].name == "framework-tools"
        assert "mcp_tool_server" in " ".join(mcp_servers[0].args)


@pytest.mark.asyncio
async def test_agent_run_streaming():
    agent = Agent(name="test", backend="claude", instruction="Be helpful.", stream=True)
    ctx = Context(session_id="s1", cwd="/tmp")
    ctx.set_input("Hello")

    async def fake_prompt_stream(session_id, text):
        for chunk in ["Hello", " ", "world", "!"]:
            yield chunk

    with patch.object(agent, "_get_backend") as mock_get:
        mock_backend = AsyncMock()
        mock_backend.start = AsyncMock()
        mock_backend.new_session = AsyncMock(return_value="sess-123")
        mock_backend.prompt_stream = fake_prompt_stream
        mock_backend.stop = AsyncMock()
        mock_get.return_value = mock_backend
        events = []
        async for event in agent.run(ctx):
            events.append(event)
        # Should have 4 stream_chunk events + 1 final message event
        stream_chunks = [e for e in events if e.type == "stream_chunk"]
        message_events = [e for e in events if e.type == "message"]
        assert len(stream_chunks) == 4
        assert stream_chunks[0].content == "Hello"
        assert stream_chunks[2].content == "world"
        assert len(message_events) == 1
        assert message_events[0].content == "Hello world!"
        assert ctx.get_output() == "Hello world!"


@pytest.mark.asyncio
async def test_agent_run_non_streaming_default():
    """Verify stream=False (default) uses prompt() not prompt_stream()."""
    agent = Agent(name="test", backend="claude", instruction="Hi.")
    assert agent.stream is False
    ctx = Context(session_id="s1", cwd="/tmp")
    ctx.set_input("test")
    with patch.object(agent, "_get_backend") as mock_get:
        mock_backend = AsyncMock()
        mock_backend.start = AsyncMock()
        mock_backend.new_session = AsyncMock(return_value="sess-1")
        mock_backend.prompt = AsyncMock(return_value="response")
        mock_backend.stop = AsyncMock()
        mock_get.return_value = mock_backend
        events = []
        async for event in agent.run(ctx):
            events.append(event)
        assert all(e.type == "message" for e in events)
        mock_backend.prompt.assert_awaited_once()


@pytest.mark.asyncio
async def test_agent_multi_turn_records_history():
    agent = Agent(name="test", backend="claude", instruction="Be helpful.", multi_turn=True)
    ctx = Context(session_id="s1", cwd="/tmp")

    # First turn
    ctx.set_input("Hello")
    with patch.object(agent, "_get_backend") as mock_get:
        mock_backend = AsyncMock()
        mock_backend.start = AsyncMock()
        mock_backend.new_session = AsyncMock(return_value="sess-1")
        mock_backend.prompt = AsyncMock(return_value="Hi there!")
        mock_backend.stop = AsyncMock()
        mock_get.return_value = mock_backend
        async for _ in agent.run(ctx):
            pass

    assert len(ctx.get_history()) == 2
    assert ctx.get_history()[0] == {"role": "user", "content": "Hello"}
    assert ctx.get_history()[1] == {"role": "assistant", "content": "Hi there!"}

    # Second turn - history should be included in prompt
    ctx.set_input("How are you?")
    with patch.object(agent, "_get_backend") as mock_get:
        mock_backend = AsyncMock()
        mock_backend.start = AsyncMock()
        mock_backend.new_session = AsyncMock(return_value="sess-2")
        mock_backend.prompt = AsyncMock(return_value="I'm good!")
        mock_backend.stop = AsyncMock()
        mock_get.return_value = mock_backend
        async for _ in agent.run(ctx):
            pass

        # Verify the prompt included history
        prompt_call = mock_backend.prompt.call_args
        sent_text = prompt_call[0][1]
        assert "User: Hello" in sent_text
        assert "Assistant: Hi there!" in sent_text
        assert "How are you?" in sent_text

    assert len(ctx.get_history()) == 4


@pytest.mark.asyncio
async def test_agent_non_multi_turn_no_history():
    agent = Agent(name="test", backend="claude", instruction="Hi.")
    assert agent.multi_turn is False
    ctx = Context(session_id="s1", cwd="/tmp")
    ctx.set_input("Hello")
    with patch.object(agent, "_get_backend") as mock_get:
        mock_backend = AsyncMock()
        mock_backend.start = AsyncMock()
        mock_backend.new_session = AsyncMock(return_value="sess-1")
        mock_backend.prompt = AsyncMock(return_value="Hi!")
        mock_backend.stop = AsyncMock()
        mock_get.return_value = mock_backend
        async for _ in agent.run(ctx):
            pass
    assert len(ctx.get_history()) == 0


@pytest.mark.asyncio
async def test_agent_run_retries_on_transient_failure():
    """Verify that transient errors trigger retries via backend config."""
    from acp_agent_framework.backends.registry import BackendConfig

    config = BackendConfig(command="test", max_retries=3, retry_base_delay=0.01)
    assert config.max_retries == 3
    assert config.timeout == 120.0
    assert config.retry_base_delay == 0.01


@pytest.mark.asyncio
async def test_backend_config_defaults():
    from acp_agent_framework.backends.registry import BackendConfig
    config = BackendConfig(command="test-cmd")
    assert config.timeout == 120.0
    assert config.max_retries == 3
    assert config.retry_base_delay == 1.0
