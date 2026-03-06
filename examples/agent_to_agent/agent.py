"""Agent-to-agent communication via AgentTool.

One agent wraps another as a tool, enabling delegation.
The "manager" agent can ask the "specialist" agent for help.

Usage:
    ACP_BACKEND=gemini python examples/agent_to_agent/agent.py
"""
import asyncio
import os
import sys

from acp_agent_framework import Agent, AgentTool, Context, serve


# ── Specialist agent (called as a tool by the manager) ───────────────────

translator = Agent(
    name="translator",
    backend=os.environ.get("ACP_BACKEND", "gemini"),
    instruction=(
        "You are a translator. Translate the given text to the requested "
        "language. Only output the translation, nothing else."
    ),
)

summarizer = Agent(
    name="summarizer",
    backend=os.environ.get("ACP_BACKEND", "gemini"),
    instruction=(
        "You are a summarizer. Condense the given text into 2-3 sentences. "
        "Only output the summary, nothing else."
    ),
)

# ── Manager agent (delegates to specialists) ─────────────────────────────

manager = Agent(
    name="content-manager",
    backend=os.environ.get("ACP_BACKEND", "gemini"),
    instruction=(
        "You are a content manager. You have access to a translator agent and "
        "a summarizer agent. Use them to help the user process text. "
        "When the user wants translation, use the translator tool. "
        "When they want a summary, use the summarizer tool. "
        "You can chain them: summarize first, then translate."
    ),
    tools=[
        AgentTool(translator, cwd=os.getcwd()),
        AgentTool(summarizer, cwd=os.getcwd()),
    ],
)


async def one_shot(query: str) -> None:
    ctx = Context(session_id="demo", cwd=os.getcwd())
    ctx.set_input(query)
    async for event in manager.run(ctx):
        if event.type == "message":
            print(event.content)


if __name__ == "__main__":
    if "--query" in sys.argv:
        idx = sys.argv.index("--query")
        query = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "Summarize: The ACP protocol standardizes communication between editors and AI agents."
        asyncio.run(one_shot(query))
    else:
        serve(manager)
