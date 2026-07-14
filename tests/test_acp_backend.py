import asyncio

import pytest
from acp import helpers
from pydantic import ValidationError

from acp_agent_framework.backends.acp_backend import AcpBackend
from acp_agent_framework.backends.registry import BackendConfig


def test_acp_backend_creation():
    config = BackendConfig(command="echo", args=["hello"])
    backend = AcpBackend(config)
    assert backend.config == config
    assert not backend.is_running


@pytest.mark.asyncio
async def test_acp_backend_spawn_invalid_command():
    config = BackendConfig(command="nonexistent-command-12345")
    backend = AcpBackend(config)
    with pytest.raises(Exception):
        await backend.start()


@pytest.mark.asyncio
async def test_acp_backend_start_missing_command_raises():
    config = BackendConfig(command="definitely-not-a-real-binary-xyz")
    backend = AcpBackend(config)
    with pytest.raises(RuntimeError, match="definitely-not-a-real-binary-xyz") as exc_info:
        await backend.start()
    assert "definitely-not-a-real-binary-xyz" in str(exc_info.value)


def test_backend_config_rejects_invalid_timeout():
    with pytest.raises(ValidationError):
        BackendConfig(command="echo", timeout=0)
    with pytest.raises(ValidationError):
        BackendConfig(command="echo", timeout=-1)


def test_backend_config_rejects_invalid_retries():
    with pytest.raises(ValidationError):
        BackendConfig(command="echo", max_retries=0)
    with pytest.raises(ValidationError):
        BackendConfig(command="echo", max_retries=-1)


def test_backend_config_rejects_negative_delay():
    with pytest.raises(ValidationError):
        BackendConfig(command="echo", retry_base_delay=-0.5)


class _FakeStreamingConnection:
    """Connection whose prompt() emits session updates incrementally."""

    def __init__(self, client, *, fail: bool = False):
        self._client = client
        self._fail = fail
        self.prompt_finished = False

    async def prompt(self, session_id: str, prompt, **kwargs):
        if self._fail:
            raise RuntimeError("backend prompt failed")
        await self._client.session_update(
            session_id, helpers.update_agent_message_text("Hello")
        )
        await asyncio.sleep(0)
        await self._client.session_update(
            session_id, helpers.update_agent_thought_text("internal reasoning")
        )
        await asyncio.sleep(0)
        await self._client.session_update(
            session_id, helpers.update_agent_message_text(" world")
        )
        await asyncio.sleep(0)
        self.prompt_finished = True


@pytest.mark.asyncio
async def test_prompt_stream_yields_live_message_chunks_excludes_thoughts():
    backend = AcpBackend(BackendConfig(command="echo", timeout=5.0))
    fake = _FakeStreamingConnection(backend._client)
    backend._connection = fake

    chunks = []
    first_chunk_while_running = None
    async for chunk in backend.prompt_stream("sess-1", "hi"):
        if first_chunk_while_running is None:
            first_chunk_while_running = not fake.prompt_finished
        chunks.append(chunk)

    assert chunks == ["Hello", " world"]
    assert first_chunk_while_running is True
    assert "internal reasoning" not in "".join(chunks)
    assert fake.prompt_finished is True
    assert backend._client.stream_queue is None


@pytest.mark.asyncio
async def test_prompt_excludes_thought_text_from_response():
    backend = AcpBackend(BackendConfig(command="echo", timeout=5.0, max_retries=1))
    fake = _FakeStreamingConnection(backend._client)
    backend._connection = fake

    text = await backend.prompt("sess-1", "hi")
    assert text == "Hello world"
    assert "internal reasoning" not in text


@pytest.mark.asyncio
async def test_prompt_stream_propagates_backend_errors():
    backend = AcpBackend(BackendConfig(command="echo", timeout=5.0))
    fake = _FakeStreamingConnection(backend._client, fail=True)
    backend._connection = fake

    with pytest.raises(RuntimeError, match="backend prompt failed"):
        async for _ in backend.prompt_stream("sess-1", "hi"):
            pass
    assert backend._client.stream_queue is None
