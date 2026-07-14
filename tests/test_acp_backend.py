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


class _SlowStreamingConnection:
    """Connection that sleeps between updates so the consumer can aclose mid-stream."""

    def __init__(self, client):
        self._client = client

    async def prompt(self, session_id: str, prompt, **kwargs):
        await self._client.session_update(
            session_id, helpers.update_agent_message_text("chunk1")
        )
        await asyncio.sleep(0.05)
        await self._client.session_update(
            session_id, helpers.update_agent_message_text("chunk2")
        )
        await asyncio.sleep(0.05)
        await self._client.session_update(
            session_id, helpers.update_agent_message_text("chunk3")
        )


class _SleepyPromptConnection:
    """Connection that records prompts and sleeps so concurrent calls can race."""

    def __init__(self, client):
        self._client = client
        self.prompts: list[str] = []

    async def prompt(self, session_id: str, prompt, **kwargs):
        text = prompt[0].text if prompt else ""
        self.prompts.append(text)
        await asyncio.sleep(0.02)
        await self._client.session_update(
            session_id, helpers.update_agent_message_text(f"resp:{text}")
        )


@pytest.mark.asyncio
async def test_prompt_stream_aclose_cancels_pending_queue_get():
    """F5: closing the stream generator cancels both prompt and pending queue.get tasks."""
    backend = AcpBackend(BackendConfig(command="echo", timeout=5.0))
    fake = _SlowStreamingConnection(backend._client)
    backend._connection = fake

    gen = backend.prompt_stream("sess-1", "hi")
    first = await gen.__anext__()
    assert first == "chunk1"
    await gen.aclose()

    # Allow cancelled tasks to settle
    await asyncio.sleep(0)
    pending = [t for t in asyncio.all_tasks() if not t.done()]
    assert len(pending) == 1  # just the test task
    assert backend._client.stream_queue is None


@pytest.mark.asyncio
async def test_concurrent_prompt_serializes_without_interleaving():
    """F3: concurrent prompt() calls on one backend do not interleave/truncate."""
    backend = AcpBackend(BackendConfig(command="echo", timeout=5.0, max_retries=1))
    fake = _SleepyPromptConnection(backend._client)
    backend._connection = fake

    r1, r2 = await asyncio.gather(
        backend.prompt("sess-1", "alpha"),
        backend.prompt("sess-1", "beta"),
    )

    assert {r1, r2} == {"resp:alpha", "resp:beta"}
    assert set(fake.prompts) == {"alpha", "beta"}


@pytest.mark.asyncio
async def test_start_respects_config_env_path(tmp_path):
    """F8: which() must search config.env PATH, not only the process PATH."""
    stub_name = "fake-acp-backend-stub"
    stub = tmp_path / stub_name
    stub.write_text("#!/bin/sh\nexit 1\n")
    stub.chmod(0o755)

    config = BackendConfig(command=stub_name, env={"PATH": str(tmp_path)})
    backend = AcpBackend(config)

    with pytest.raises(Exception) as exc_info:
        await backend.start()

    # Preflight which() passed; failure is at connect/initialize, not "command not found"
    assert "Backend command not found" not in str(exc_info.value)
