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


def test_serve_acp_awaits_run_agent(monkeypatch):
    """acp.run_agent is a coroutine in SDK 0.11+; serve must actually await it."""
    import acp

    ran = {}

    async def fake_run_agent(fw_agent, *args, **kwargs):
        ran["agent"] = fw_agent

    monkeypatch.setattr(acp, "run_agent", fake_run_agent)
    serve(MockAgent(name="test"), transport="acp")
    assert "agent" in ran
