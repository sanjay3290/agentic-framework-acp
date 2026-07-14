"""Tests for per-session backend lifecycle (spawn once, reuse, close)."""
import pytest

from acp_agent_framework.agents.agent import Agent
from acp_agent_framework.context import Context


class FakeBackend:
    """Minimal stand-in for AcpBackend with call counters."""

    def __init__(self, responses: list[str] | None = None, prompt_error: Exception | None = None):
        self.start_calls = 0
        self.new_session_calls = 0
        self.stop_calls = 0
        self.prompts: list[str] = []
        self._running = False
        self._responses = list(responses) if responses is not None else ["ok"]
        self._response_idx = 0
        self._prompt_error = prompt_error

    @property
    def is_running(self) -> bool:
        return self._running

    @is_running.setter
    def is_running(self, value: bool) -> None:
        self._running = value

    async def start(self) -> None:
        self.start_calls += 1
        self._running = True

    async def new_session(self, cwd: str, mcp_servers=None) -> str:
        self.new_session_calls += 1
        return "fake-session"

    async def prompt(self, session_id: str, text: str) -> str:
        if self._prompt_error is not None:
            raise self._prompt_error
        self.prompts.append(text)
        if self._response_idx < len(self._responses):
            response = self._responses[self._response_idx]
            self._response_idx += 1
            return response
        return self._responses[-1]

    async def prompt_stream(self, session_id: str, text: str):
        response = await self.prompt(session_id, text)
        yield response

    async def stop(self) -> None:
        self.stop_calls += 1
        self._running = False


def _install_backend_factory(monkeypatch, backends: list[FakeBackend] | None = None):
    """Patch Agent._get_backend to return a new FakeBackend each spawn."""
    created = backends if backends is not None else []

    def _get_backend(self):
        backend = FakeBackend()
        created.append(backend)
        return backend

    monkeypatch.setattr(Agent, "_get_backend", _get_backend)
    return created


async def _run(agent: Agent, ctx: Context, text: str) -> None:
    ctx.set_input(text)
    async for _ in agent.run(ctx):
        pass


@pytest.mark.asyncio
async def test_backend_reused_across_runs(monkeypatch):
    backends = _install_backend_factory(monkeypatch)
    agent = Agent(name="assistant", backend="claude", instruction="Be helpful.")
    ctx = Context(session_id="s1", cwd="/tmp")

    await _run(agent, ctx, "first")
    await _run(agent, ctx, "second")

    assert len(backends) == 1
    backend = backends[0]
    assert backend.start_calls == 1
    assert backend.new_session_calls == 1
    assert len(backend.prompts) == 2
    assert backend.stop_calls == 0
    assert "Be helpful." in backend.prompts[0]
    assert "first" in backend.prompts[0]
    assert "Be helpful." not in backend.prompts[1]
    assert backend.prompts[1] == "second"


@pytest.mark.asyncio
async def test_ctx_close_stops_backend_and_respawns(monkeypatch):
    backends = _install_backend_factory(monkeypatch)
    agent = Agent(name="assistant", backend="claude", instruction="Be helpful.")
    ctx = Context(session_id="s1", cwd="/tmp")

    await _run(agent, ctx, "first")
    assert backends[0].stop_calls == 0

    await ctx.close()
    assert backends[0].stop_calls == 1
    assert ctx.get_resource("backend:assistant") is None

    await _run(agent, ctx, "after-close")
    assert len(backends) == 2
    assert backends[1].start_calls == 1
    assert backends[1].new_session_calls == 1
    assert "Be helpful." in backends[1].prompts[0]


@pytest.mark.asyncio
async def test_dead_backend_respawns_and_resends_instruction(monkeypatch):
    backends = _install_backend_factory(monkeypatch)
    agent = Agent(name="assistant", backend="claude", instruction="System prompt.")
    ctx = Context(session_id="s1", cwd="/tmp")

    await _run(agent, ctx, "turn-1")
    old = backends[0]
    assert old.start_calls == 1
    assert "System prompt." in old.prompts[0]

    # Simulate process death without going through stop()
    old.is_running = False

    await _run(agent, ctx, "turn-2")

    assert old.stop_calls == 1  # aclose of the dead session
    assert len(backends) == 2
    fresh = backends[1]
    assert fresh.start_calls == 1
    assert fresh.new_session_calls == 1
    assert "System prompt." in fresh.prompts[0]
    assert "turn-2" in fresh.prompts[0]


@pytest.mark.asyncio
async def test_multi_turn_warm_backend_skips_history_replay(monkeypatch):
    backends = _install_backend_factory(monkeypatch)
    agent = Agent(
        name="assistant",
        backend="claude",
        instruction="Remember context.",
        multi_turn=True,
    )
    ctx = Context(session_id="s1", cwd="/tmp")

    await _run(agent, ctx, "Hello")
    await _run(agent, ctx, "How are you?")

    assert len(backends) == 1
    backend = backends[0]
    assert len(backend.prompts) == 2
    assert "Remember context." in backend.prompts[0]
    assert "User:" not in backend.prompts[0]  # no prior history on first turn
    # Warm backend: only the new user input
    assert backend.prompts[1] == "How are you?"
    assert "Remember context." not in backend.prompts[1]
    assert "User: Hello" not in backend.prompts[1]
    assert len(ctx.get_history()) == 4


@pytest.mark.asyncio
async def test_multi_turn_fresh_backend_replays_history(monkeypatch):
    backends = _install_backend_factory(monkeypatch)
    agent = Agent(
        name="assistant",
        backend="claude",
        instruction="Remember context.",
        multi_turn=True,
    )
    ctx = Context(session_id="s1", cwd="/tmp")

    await _run(agent, ctx, "Hello")
    await _run(agent, ctx, "How are you?")
    assert len(ctx.get_history()) == 4

    # Close releases the warm backend but keeps conversation history
    await ctx.close()

    await _run(agent, ctx, "What did I say?")

    assert len(backends) == 2
    fresh_prompt = backends[1].prompts[0]
    assert "Remember context." in fresh_prompt
    assert "User: Hello" in fresh_prompt
    assert "Assistant:" in fresh_prompt
    assert "What did I say?" in fresh_prompt


@pytest.mark.asyncio
async def test_prompt_exception_removes_resource_and_stops(monkeypatch):
    created: list[FakeBackend] = []

    def _get_backend(self):
        backend = FakeBackend(prompt_error=RuntimeError("backend blew up"))
        created.append(backend)
        return backend

    monkeypatch.setattr(Agent, "_get_backend", _get_backend)
    agent = Agent(name="assistant", backend="claude", instruction="Hi.")
    ctx = Context(session_id="s1", cwd="/tmp")

    with pytest.raises(RuntimeError, match="backend blew up"):
        await _run(agent, ctx, "boom")

    assert len(created) == 1
    assert created[0].stop_calls == 1
    assert ctx.get_resource("backend:assistant") is None

    # Next run can spawn a healthy backend
    healthy = FakeBackend(responses=["recovered"])

    def _get_healthy(self):
        return healthy

    monkeypatch.setattr(Agent, "_get_backend", _get_healthy)
    await _run(agent, ctx, "ok now")
    assert healthy.start_calls == 1
    assert ctx.get_output() == "recovered"
