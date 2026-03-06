import pytest
from unittest.mock import AsyncMock, patch
from acp_agent_framework.guardrails import Guardrail, GuardrailError
from acp_agent_framework.agents.agent import Agent
from acp_agent_framework.context import Context


def test_guardrail_creation():
    g = Guardrail("test", lambda text: text.upper())
    assert g.name == "test"


def test_guardrail_validate_transforms():
    g = Guardrail("upper", lambda text: text.upper())
    assert g.validate("hello") == "HELLO"


def test_guardrail_validate_passthrough():
    """Returning None means no transformation, pass text through."""
    g = Guardrail("noop", lambda text: None)
    assert g.validate("hello") == "hello"


def test_guardrail_validate_raises():
    def block_bad_words(text):
        if "blocked" in text.lower():
            raise GuardrailError("Blocked content detected", guardrail_name="blocker")
        return None

    g = Guardrail("blocker", block_bad_words)
    assert g.validate("safe text") == "safe text"
    with pytest.raises(GuardrailError, match="Blocked content"):
        g.validate("this is blocked content")


def test_guardrail_error_has_name():
    err = GuardrailError("bad input", guardrail_name="my-guard")
    assert err.guardrail_name == "my-guard"
    assert str(err) == "bad input"


@pytest.mark.asyncio
async def test_agent_input_guardrail():
    def redact_secrets(text):
        return text.replace("SECRET123", "[REDACTED]")

    guardrail = Guardrail("redact", redact_secrets)
    agent = Agent(
        name="test",
        backend="claude",
        instruction="Be helpful.",
        input_guardrails=[guardrail],
    )
    ctx = Context(session_id="s1", cwd="/tmp")
    ctx.set_input("My password is SECRET123")

    with patch.object(agent, "_get_backend") as mock_get:
        mock_backend = AsyncMock()
        mock_backend.start = AsyncMock()
        mock_backend.new_session = AsyncMock(return_value="sess-1")
        mock_backend.prompt = AsyncMock(return_value="OK")
        mock_backend.stop = AsyncMock()
        mock_get.return_value = mock_backend
        async for _ in agent.run(ctx):
            pass
        # Verify the prompt was redacted before sending
        sent_text = mock_backend.prompt.call_args[0][1]
        assert "SECRET123" not in sent_text
        assert "[REDACTED]" in sent_text


@pytest.mark.asyncio
async def test_agent_output_guardrail():
    def sanitize_output(text):
        return text.replace("internal-url", "[REMOVED]")

    guardrail = Guardrail("sanitize", sanitize_output)
    agent = Agent(
        name="test",
        backend="claude",
        instruction="Be helpful.",
        output_guardrails=[guardrail],
    )
    ctx = Context(session_id="s1", cwd="/tmp")
    ctx.set_input("Tell me something")

    with patch.object(agent, "_get_backend") as mock_get:
        mock_backend = AsyncMock()
        mock_backend.start = AsyncMock()
        mock_backend.new_session = AsyncMock(return_value="sess-1")
        mock_backend.prompt = AsyncMock(return_value="Visit internal-url for details")
        mock_backend.stop = AsyncMock()
        mock_get.return_value = mock_backend
        events = []
        async for event in agent.run(ctx):
            events.append(event)
        message = [e for e in events if e.type == "message"][0]
        assert "internal-url" not in message.content
        assert "[REMOVED]" in message.content
        assert ctx.get_output() == "Visit [REMOVED] for details"


@pytest.mark.asyncio
async def test_agent_guardrail_raises_blocks_execution():
    def block_all(text):
        raise GuardrailError("Input blocked", guardrail_name="blocker")

    guardrail = Guardrail("blocker", block_all)
    agent = Agent(
        name="test",
        backend="claude",
        instruction="Be helpful.",
        input_guardrails=[guardrail],
    )
    ctx = Context(session_id="s1", cwd="/tmp")
    ctx.set_input("Hello")

    with patch.object(agent, "_get_backend") as mock_get:
        mock_backend = AsyncMock()
        mock_backend.start = AsyncMock()
        mock_backend.new_session = AsyncMock(return_value="sess-1")
        mock_backend.prompt = AsyncMock(return_value="Should not reach")
        mock_backend.stop = AsyncMock()
        mock_get.return_value = mock_backend
        with pytest.raises(GuardrailError, match="Input blocked"):
            async for _ in agent.run(ctx):
                pass
