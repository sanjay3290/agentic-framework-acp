import pytest
from acp_agent_framework.server.acp_server import FrameworkAgent
from acp_agent_framework.agents.base import BaseAgent
from acp_agent_framework.context import Context
from acp_agent_framework.events import Event
import acp


class MockAgent(BaseAgent):
    name: str = "test"

    def __init__(self, name: str, output: str):
        super().__init__(name=name)
        object.__setattr__(self, "_output", output)

    async def run(self, ctx: Context):
        ctx.set_output(self._output)
        yield Event(author=self.name, type="message", content=self._output)


class StreamingMockAgent(BaseAgent):
    name: str = "stream-test"

    async def run(self, ctx: Context):
        yield Event(author=self.name, type="stream_chunk", content="Hello")
        yield Event(author=self.name, type="stream_chunk", content=" world")
        full = "Hello world"
        ctx.set_output(full)
        yield Event(author=self.name, type="message", content=full)


class GuardedStreamingMockAgent(BaseAgent):
    """Stream chunks then a final message that differs (e.g. output guardrails)."""

    name: str = "guarded-stream"

    async def run(self, ctx: Context):
        yield Event(author=self.name, type="stream_chunk", content="Hello")
        yield Event(author=self.name, type="stream_chunk", content=" world")
        final = "Hello world [guarded]"
        ctx.set_output(final)
        yield Event(author=self.name, type="message", content=final)


@pytest.mark.asyncio
async def test_framework_agent_initialize():
    agent = MockAgent("test", "hello")
    fw_agent = FrameworkAgent(agent)
    result = await fw_agent.initialize(
        protocol_version=acp.PROTOCOL_VERSION,
        client_info=acp.schema.Implementation(name="test", version="0.1.0"),
    )
    assert result.protocol_version == acp.PROTOCOL_VERSION
    assert result.agent_info.name == "test"


@pytest.mark.asyncio
async def test_framework_agent_new_session():
    agent = MockAgent("test", "hello")
    fw_agent = FrameworkAgent(agent)
    result = await fw_agent.new_session(cwd="/tmp/test")
    assert result.session_id is not None
    assert len(result.session_id) > 0


@pytest.mark.asyncio
async def test_framework_agent_prompt():
    agent = MockAgent("test", "hello response")
    fw_agent = FrameworkAgent(agent)
    session = await fw_agent.new_session(cwd="/tmp/test")
    result = await fw_agent.prompt(
        prompt=[acp.schema.TextContentBlock(type="text", text="Hi")],
        session_id=session.session_id,
    )
    assert result.stop_reason == "end_turn"


class FakeAgentConnection:
    def __init__(self):
        self.calls = []

    async def session_update(self, session_id, update, **kwargs):
        self.calls.append((session_id, update))


@pytest.mark.asyncio
async def test_framework_agent_prompt_delivers_session_updates():
    agent = MockAgent("test", "hello response")
    fw_agent = FrameworkAgent(agent)
    fake_conn = FakeAgentConnection()
    fw_agent.on_connect(fake_conn)
    session = await fw_agent.new_session(cwd="/tmp/test")
    result = await fw_agent.prompt(
        prompt=[acp.schema.TextContentBlock(type="text", text="Hi")],
        session_id=session.session_id,
    )
    assert len(fake_conn.calls) == 1
    recorded_session_id, update = fake_conn.calls[0]
    assert recorded_session_id == session.session_id
    assert isinstance(update, acp.schema.AgentMessageChunk)
    assert update.content.text == "hello response"
    assert result.stop_reason == "end_turn"


@pytest.mark.asyncio
async def test_framework_agent_prompt_forwards_stream_chunks_skips_final_message():
    agent = StreamingMockAgent()
    fw_agent = FrameworkAgent(agent)
    fake_conn = FakeAgentConnection()
    fw_agent.on_connect(fake_conn)
    session = await fw_agent.new_session(cwd="/tmp/test")
    result = await fw_agent.prompt(
        prompt=[acp.schema.TextContentBlock(type="text", text="Hi")],
        session_id=session.session_id,
    )
    assert len(fake_conn.calls) == 2
    texts = [update.content.text for _, update in fake_conn.calls]
    assert texts == ["Hello", " world"]
    for _, update in fake_conn.calls:
        assert isinstance(update, acp.schema.AgentMessageChunk)
    assert result.stop_reason == "end_turn"


@pytest.mark.asyncio
async def test_framework_agent_prompt_non_streaming_still_forwards_message():
    agent = MockAgent("test", "only final")
    fw_agent = FrameworkAgent(agent)
    fake_conn = FakeAgentConnection()
    fw_agent.on_connect(fake_conn)
    session = await fw_agent.new_session(cwd="/tmp/test")
    await fw_agent.prompt(
        prompt=[acp.schema.TextContentBlock(type="text", text="Hi")],
        session_id=session.session_id,
    )
    assert len(fake_conn.calls) == 1
    assert fake_conn.calls[0][1].content.text == "only final"


@pytest.mark.asyncio
async def test_framework_agent_pipeline_streaming_then_plain_agent():
    """A later agent's message must not be suppressed by an earlier agent's chunks."""
    class MixedPipelineAgent(BaseAgent):
        name: str = "pipeline"

        async def run(self, ctx: Context):
            yield Event(author="streamer", type="stream_chunk", content="chunk-a")
            yield Event(author="streamer", type="stream_chunk", content="chunk-b")
            yield Event(author="streamer", type="message", content="chunk-achunk-b")
            yield Event(author="plain", type="message", content="second agent output")

    fw_agent = FrameworkAgent(MixedPipelineAgent())
    fake_conn = FakeAgentConnection()
    fw_agent.on_connect(fake_conn)
    session = await fw_agent.new_session(cwd="/tmp/test")
    await fw_agent.prompt(
        prompt=[acp.schema.TextContentBlock(type="text", text="Hi")],
        session_id=session.session_id,
    )
    texts = [update.content.text for _, update in fake_conn.calls]
    assert texts == ["chunk-a", "chunk-b", "second agent output"]


@pytest.mark.asyncio
async def test_framework_agent_prompt_forwards_final_when_differs_from_chunks():
    """F9: when final message content differs from joined chunks, forward it too."""
    agent = GuardedStreamingMockAgent()
    fw_agent = FrameworkAgent(agent)
    fake_conn = FakeAgentConnection()
    fw_agent.on_connect(fake_conn)
    session = await fw_agent.new_session(cwd="/tmp/test")
    result = await fw_agent.prompt(
        prompt=[acp.schema.TextContentBlock(type="text", text="Hi")],
        session_id=session.session_id,
    )
    texts = [update.content.text for _, update in fake_conn.calls]
    assert texts == ["Hello", " world", "Hello world [guarded]"]
    assert len(fake_conn.calls) == 3
    assert result.stop_reason == "end_turn"


@pytest.mark.asyncio
async def test_close_session_removes_session_and_closes_resources():
    """F4: close_session pops the session and closes its context resources."""

    class SentinelResource:
        def __init__(self):
            self.closed = False

        async def aclose(self):
            self.closed = True

    agent = MockAgent("test", "hello")
    fw_agent = FrameworkAgent(agent)
    session = await fw_agent.new_session(cwd="/tmp/test")
    sid = session.session_id
    ctx = fw_agent._sessions[sid]
    sentinel = SentinelResource()
    ctx.set_resource("sentinel", sentinel)

    await fw_agent.prompt(
        prompt=[acp.schema.TextContentBlock(type="text", text="Hi")],
        session_id=sid,
    )
    await fw_agent.close_session(sid)

    assert sid not in fw_agent._sessions
    assert sentinel.closed is True
    with pytest.raises(acp.RequestError):
        await fw_agent.prompt(
            prompt=[acp.schema.TextContentBlock(type="text", text="again")],
            session_id=sid,
        )


@pytest.mark.asyncio
async def test_shutdown_closes_all_sessions():
    """F4: shutdown closes every session context."""

    class SentinelResource:
        def __init__(self):
            self.closed = False

        async def aclose(self):
            self.closed = True

    agent = MockAgent("test", "hello")
    fw_agent = FrameworkAgent(agent)
    s1 = await fw_agent.new_session(cwd="/tmp/a")
    s2 = await fw_agent.new_session(cwd="/tmp/b")
    sentinels = []
    for sid in (s1.session_id, s2.session_id):
        res = SentinelResource()
        fw_agent._sessions[sid].set_resource("sentinel", res)
        sentinels.append(res)

    await fw_agent.shutdown()

    assert fw_agent._sessions == {}
    assert all(s.closed for s in sentinels)
