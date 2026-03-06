"""Simple single-agent example using Claude as backend."""
from acp_agent_framework import Agent, serve

agent = Agent(
    name="simple-assistant",
    backend="claude",
    instruction="You are a helpful coding assistant. Be concise.",
)

if __name__ == "__main__":
    serve(agent)
