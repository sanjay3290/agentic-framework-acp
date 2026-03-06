from fastapi.testclient import TestClient
from acp_agent_framework.server.http_server import create_app
from acp_agent_framework.agents.base import BaseAgent
from acp_agent_framework.context import Context
from acp_agent_framework.events import Event


class MockAgent(BaseAgent):
    name: str = "test"

    def __init__(self, name: str = "test"):
        super().__init__(name=name)

    async def run(self, ctx: Context):
        yield Event(author=self.name, type="message", content="ok")


def _make_client():
    return TestClient(create_app(MockAgent()))


def test_root_returns_html():
    client = _make_client()
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "ACP Agent Dashboard" in resp.text


def test_static_files_served():
    client = _make_client()
    resp = client.get("/static/index.html")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
