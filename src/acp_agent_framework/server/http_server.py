"""HTTP server exposing agents via REST API with SSE streaming."""
import json
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from acp_agent_framework.agents.base import BaseAgent
from acp_agent_framework.context import Context

_static_dir = Path(__file__).parent / "static"


class CreateSessionRequest(BaseModel):
    cwd: str


class PromptRequest(BaseModel):
    text: str


class SessionResponse(BaseModel):
    session_id: str
    cwd: str


def create_app(agent: BaseAgent) -> FastAPI:
    app = FastAPI(title=f"ACP Agent: {agent.name}")
    sessions: dict[str, Context] = {}

    @app.get("/")
    async def root():
        return FileResponse(_static_dir / "index.html")

    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

    @app.post("/api/sessions")
    async def create_session(req: CreateSessionRequest) -> SessionResponse:
        session_id = str(uuid.uuid4())
        ctx = Context(session_id=session_id, cwd=req.cwd)
        sessions[session_id] = ctx
        return SessionResponse(session_id=session_id, cwd=req.cwd)

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str) -> SessionResponse:
        ctx = sessions.get(session_id)
        if not ctx:
            raise HTTPException(status_code=404, detail="Session not found")
        return SessionResponse(session_id=session_id, cwd=ctx.cwd)

    @app.delete("/api/sessions/{session_id}")
    async def delete_session(session_id: str) -> dict:
        if session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        del sessions[session_id]
        return {"status": "deleted"}

    @app.post("/api/sessions/{session_id}/prompt")
    async def prompt_endpoint(session_id: str, req: PromptRequest) -> StreamingResponse:
        ctx = sessions.get(session_id)
        if not ctx:
            raise HTTPException(status_code=404, detail="Session not found")
        ctx.set_input(req.text)

        async def event_stream():
            async for event in agent.run(ctx):
                data = json.dumps(
                    {
                        "id": event.id,
                        "author": event.author,
                        "type": event.type,
                        "content": str(event.content),
                    }
                )
                yield f"data: {data}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    return app
