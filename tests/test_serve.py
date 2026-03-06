from acp_agent_framework.server.serve import serve
from acp_agent_framework.agents.base import BaseAgent
from acp_agent_framework.context import Context
from acp_agent_framework.events import Event
import pytest


class MockAgent(BaseAgent):
    name: str = "test"

    async def run(self, ctx: Context):
        yield Event(author=self.name, type="message", content="hello")


def test_serve_invalid_transport():
    agent = MockAgent(name="test")
    with pytest.raises(ValueError, match="Unknown transport"):
        serve(agent, transport="invalid")
