from fastapi.testclient import TestClient
from acp_agent_framework.server.http_server import create_app
from acp_agent_framework.agents.base import BaseAgent
from acp_agent_framework.context import Context
from acp_agent_framework.events import Event


class MockAgent(BaseAgent):
    name: str = "test"

    def __init__(self, name: str, output: str):
        super().__init__(name=name)
        object.__setattr__(self, "_output", output)

    async def run(self, ctx: Context):
        ctx.set_output(self._output)
        yield Event(author=self.name, type="message", content=self._output)


def test_create_session():
    agent = MockAgent("test", "hello")
    app = create_app(agent)
    client = TestClient(app)
    response = client.post("/api/sessions", json={"cwd": "/tmp/test"})
    assert response.status_code == 200
    assert "session_id" in response.json()


def test_get_session():
    agent = MockAgent("test", "hello")
    app = create_app(agent)
    client = TestClient(app)
    create_resp = client.post("/api/sessions", json={"cwd": "/tmp"})
    session_id = create_resp.json()["session_id"]
    get_resp = client.get(f"/api/sessions/{session_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["session_id"] == session_id


def test_get_unknown_session():
    agent = MockAgent("test", "hello")
    app = create_app(agent)
    client = TestClient(app)
    response = client.get("/api/sessions/nonexistent")
    assert response.status_code == 404


def test_delete_session():
    agent = MockAgent("test", "hello")
    app = create_app(agent)
    client = TestClient(app)
    create_resp = client.post("/api/sessions", json={"cwd": "/tmp"})
    session_id = create_resp.json()["session_id"]
    delete_resp = client.delete(f"/api/sessions/{session_id}")
    assert delete_resp.status_code == 200
    get_resp = client.get(f"/api/sessions/{session_id}")
    assert get_resp.status_code == 404
