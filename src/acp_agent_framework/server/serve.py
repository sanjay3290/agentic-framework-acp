"""Entry point for serving agents via ACP (stdio) or HTTP."""
from acp_agent_framework.agents.base import BaseAgent


def serve(
    agent: BaseAgent,
    transport: str = "acp",
    host: str = "0.0.0.0",
    port: int = 8000,
):
    """Serve an agent via ACP stdio or HTTP.

    Args:
        agent: The agent to serve.
        transport: "acp" for stdio ACP protocol, "http" for FastAPI REST API.
        host: Host to bind HTTP server to.
        port: Port to bind HTTP server to.
    """
    if transport == "acp":
        _serve_acp(agent)
    elif transport == "http":
        _serve_http(agent, host, port)
    else:
        raise ValueError(f"Unknown transport: {transport}. Use 'acp' or 'http'.")


def _serve_acp(agent: BaseAgent):
    import acp
    from acp_agent_framework.server.acp_server import FrameworkAgent

    fw_agent = FrameworkAgent(agent)
    acp.run_agent(fw_agent)


def _serve_http(agent: BaseAgent, host: str, port: int):
    import uvicorn
    from acp_agent_framework.server.http_server import create_app

    app = create_app(agent)
    uvicorn.run(app, host=host, port=port)
