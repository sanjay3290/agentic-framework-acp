"""Tests for example agents — validates framework constructs without live backends."""
import pytest
from unittest.mock import AsyncMock, patch

from acp_agent_framework import (
    Agent,
    AgentTool,
    Context,
    FunctionTool,
    Guardrail,
    GuardrailError,
    Route,
    RouterAgent,
    SequentialAgent,
    ToolAgent,
)


# ── FunctionTool examples ────────────────────────────────────────────────


def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


def upper(text: str) -> str:
    """Convert text to uppercase."""
    return text.upper()


def test_function_tool_schema_extraction():
    tool = FunctionTool(add)
    schema = tool.get_schema()
    assert schema["name"] == "add"
    assert schema["description"] == "Add two numbers."
    assert "a" in schema["parameters"]
    assert "b" in schema["parameters"]


def test_function_tool_sync_execution():
    tool = FunctionTool(add)
    assert tool.run({"a": 3, "b": 4}) == 7


@pytest.mark.asyncio
async def test_function_tool_async_execution():
    tool = FunctionTool(add)
    result = await tool.arun({"a": 10, "b": 20})
    assert result == 30


@pytest.mark.asyncio
async def test_function_tool_async_offloads_to_thread():
    """Sync functions should be offloaded to a thread in arun."""
    import time

    def slow_add(a: int, b: int) -> int:
        """Slow add."""
        time.sleep(0.01)
        return a + b

    tool = FunctionTool(slow_add)
    result = await tool.arun({"a": 1, "b": 2})
    assert result == 3


# ── Guardrails ───────────────────────────────────────────────────────────


def test_guardrail_transforms_input():
    g = Guardrail("upper", lambda text: text.replace("secret", "[REDACTED]"))
    assert g.validate("my secret key") == "my [REDACTED] key"


def test_guardrail_passthrough():
    g = Guardrail("noop", lambda text: None)
    assert g.validate("unchanged") == "unchanged"


def test_guardrail_blocks_on_error():
    def blocker(text):
        if "blocked" in text:
            raise GuardrailError("Content blocked", guardrail_name="blocker")
        return None

    g = Guardrail("blocker", blocker)
    assert g.validate("safe") == "safe"
    with pytest.raises(GuardrailError, match="Content blocked"):
        g.validate("this is blocked")


@pytest.mark.asyncio
async def test_agent_with_input_guardrail():
    agent = Agent(
        name="safe",
        backend="gemini",
        instruction="Be helpful.",
        input_guardrails=[Guardrail("redact", lambda t: t.replace("TOKEN123", "[REDACTED]"))],
    )
    ctx = Context(session_id="s1", cwd="/tmp")
    ctx.set_input("My token is TOKEN123")

    with patch.object(agent, "_get_backend") as mock_get:
        mock_backend = AsyncMock()
        mock_backend.start = AsyncMock()
        mock_backend.new_session = AsyncMock(return_value="sess-1")
        mock_backend.prompt = AsyncMock(return_value="OK")
        mock_backend.stop = AsyncMock()
        mock_get.return_value = mock_backend

        async for _ in agent.run(ctx):
            pass

        sent = mock_backend.prompt.call_args[0][1]
        assert "TOKEN123" not in sent
        assert "[REDACTED]" in sent


@pytest.mark.asyncio
async def test_agent_with_output_guardrail():
    agent = Agent(
        name="safe",
        backend="gemini",
        instruction="Be helpful.",
        output_guardrails=[Guardrail("limit", lambda t: t[:20] + "..." if len(t) > 20 else t)],
    )
    ctx = Context(session_id="s1", cwd="/tmp")
    ctx.set_input("Tell me something")

    with patch.object(agent, "_get_backend") as mock_get:
        mock_backend = AsyncMock()
        mock_backend.start = AsyncMock()
        mock_backend.new_session = AsyncMock(return_value="sess-1")
        mock_backend.prompt = AsyncMock(return_value="A" * 100)
        mock_backend.stop = AsyncMock()
        mock_get.return_value = mock_backend

        events = []
        async for event in agent.run(ctx):
            events.append(event)

        msg = [e for e in events if e.type == "message"][0]
        assert len(msg.content) == 23  # 20 chars + "..."
        assert msg.content.endswith("...")


# ── ToolAgent ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tool_agent_executes_directly():
    """ToolAgent runs tools without an LLM backend."""

    async def execute(ctx, tools):
        a = tools["add"].run({"a": 5, "b": 3})
        b = tools["upper"].run({"text": "hello"})
        return f"{a} {b}"

    agent = ToolAgent(
        name="direct",
        execute=execute,
        tools=[FunctionTool(add), FunctionTool(upper)],
        output_key="result",
    )

    ctx = Context(session_id="s1", cwd="/tmp")
    ctx.set_input("compute")

    events = []
    async for event in agent.run(ctx):
        events.append(event)

    assert events[0].content == "8 HELLO"
    assert ctx.state.get("result") == "8 HELLO"


# ── Sequential pipeline ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sequential_pipeline():
    """Agents in a SequentialAgent share state via output_key."""
    agent1 = Agent(name="a1", backend="gemini", instruction="Inst1", output_key="step1")
    agent2 = Agent(
        name="a2",
        backend="gemini",
        instruction=lambda ctx: f"Process: {ctx.state.get('step1', '')}",
    )

    pipeline = SequentialAgent(name="pipe", agents=[agent1, agent2])
    ctx = Context(session_id="s1", cwd="/tmp")
    ctx.set_input("start")

    with patch.object(agent1, "_get_backend") as m1, patch.object(agent2, "_get_backend") as m2:
        b1 = AsyncMock()
        b1.start = AsyncMock()
        b1.new_session = AsyncMock(return_value="s1")
        b1.prompt = AsyncMock(return_value="step1_result")
        b1.stop = AsyncMock()
        m1.return_value = b1

        b2 = AsyncMock()
        b2.start = AsyncMock()
        b2.new_session = AsyncMock(return_value="s2")
        b2.prompt = AsyncMock(return_value="final_result")
        b2.stop = AsyncMock()
        m2.return_value = b2

        events = []
        async for event in pipeline.run(ctx):
            events.append(event)

        # Agent1 stored its output
        assert ctx.state.get("step1") == "step1_result"
        # Agent2 received it in instruction
        sent = b2.prompt.call_args[0][1]
        assert "step1_result" in sent


# ── Router agent ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_router_agent_routes_by_keyword():
    code_agent = Agent(name="code", backend="gemini", instruction="Code help.")
    math_agent = Agent(name="math", backend="gemini", instruction="Math help.")

    router = RouterAgent(
        name="router",
        routes=[
            Route(keywords=["code", "python"], agent=code_agent),
            Route(keywords=["math", "calculate"], agent=math_agent),
        ],
        default_agent=code_agent,
    )

    ctx = Context(session_id="s1", cwd="/tmp")
    ctx.set_input("Calculate 2+2")

    with patch.object(math_agent, "_get_backend") as mock_get:
        mock_backend = AsyncMock()
        mock_backend.start = AsyncMock()
        mock_backend.new_session = AsyncMock(return_value="s1")
        mock_backend.prompt = AsyncMock(return_value="4")
        mock_backend.stop = AsyncMock()
        mock_get.return_value = mock_backend

        events = []
        async for event in router.run(ctx):
            events.append(event)

        # Math agent was chosen (not code)
        assert any(e.author == "math" for e in events)


# ── Multi-turn ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_multi_turn_maintains_history():
    agent = Agent(
        name="tutor",
        backend="gemini",
        instruction="Be helpful.",
        multi_turn=True,
    )

    ctx = Context(session_id="s1", cwd="/tmp")

    with patch.object(agent, "_get_backend") as mock_get:
        mock_backend = AsyncMock()
        mock_backend.start = AsyncMock()
        mock_backend.new_session = AsyncMock(return_value="s1")
        mock_backend.prompt = AsyncMock(side_effect=["Response 1", "Response 2"])
        mock_backend.stop = AsyncMock()
        mock_get.return_value = mock_backend

        # First turn
        ctx.set_input("Question 1")
        async for _ in agent.run(ctx):
            pass

        # Second turn
        ctx.set_input("Question 2")
        async for _ in agent.run(ctx):
            pass

        history = ctx.get_history()
        assert len(history) == 4  # 2 user + 2 assistant
        assert history[0] == {"role": "user", "content": "Question 1"}
        assert history[1] == {"role": "assistant", "content": "Response 1"}
        assert history[2] == {"role": "user", "content": "Question 2"}
        assert history[3] == {"role": "assistant", "content": "Response 2"}

        # Second prompt should include history
        second_prompt = mock_backend.prompt.call_args_list[1][0][1]
        assert "Question 1" in second_prompt
        assert "Response 1" in second_prompt


# ── Streaming ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_streaming_yields_chunks():
    agent = Agent(
        name="streamer",
        backend="gemini",
        instruction="Tell a story.",
        stream=True,
    )

    ctx = Context(session_id="s1", cwd="/tmp")
    ctx.set_input("Once upon a time")

    async def mock_stream(*args):
        for chunk in ["Once ", "upon ", "a time."]:
            yield chunk

    with patch.object(agent, "_get_backend") as mock_get:
        mock_backend = AsyncMock()
        mock_backend.start = AsyncMock()
        mock_backend.new_session = AsyncMock(return_value="s1")
        mock_backend.prompt_stream = mock_stream
        mock_backend.stop = AsyncMock()
        mock_get.return_value = mock_backend

        events = []
        async for event in agent.run(ctx):
            events.append(event)

        chunks = [e for e in events if e.type == "stream_chunk"]
        assert len(chunks) == 3
        assert chunks[0].content == "Once "
        assert chunks[1].content == "upon "
        assert chunks[2].content == "a time."

        # Final message is assembled from chunks
        msg = [e for e in events if e.type == "message"][0]
        assert msg.content == "Once upon a time."


# ── AgentTool ────────────────────────────────────────────────────────────


def test_agent_tool_schema():
    inner = Agent(
        name="helper",
        backend="gemini",
        instruction="Help out.",
        description="A helper agent",
    )
    tool = AgentTool(inner, cwd="/tmp")
    schema = tool.get_schema()
    assert schema["name"] == "helper"
    assert "helper" in schema["description"].lower() or "Help" in schema["description"]


# ── Context state sharing ────────────────────────────────────────────────


def test_context_state_isolation():
    ctx = Context(session_id="s1", cwd="/tmp")
    ctx.state.set("key1", "value1")
    ctx.state.set("key2", "value2")

    assert ctx.state.get("key1") == "value1"
    assert ctx.state.get("key2") == "value2"
    assert ctx.state.get("missing") is None
    assert ctx.state.get("missing", "default") == "default"
