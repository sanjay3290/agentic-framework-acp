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
