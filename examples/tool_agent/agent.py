"""ToolAgent example — runs tools directly without an LLM backend.

Useful for deterministic workflows, data pipelines, and simple
automations that don't need AI reasoning.

Usage:
    python examples/tool_agent/agent.py
"""
import asyncio
import json
import os
import urllib.request
from datetime import datetime, timezone

from acp_agent_framework import Context, FunctionTool, ToolAgent


# ── Tools ────────────────────────────────────────────────────────────────


def fetch_top_hn_stories(count: int = 5) -> str:
    """Fetch top stories from Hacker News API."""
    url = "https://hacker-news.firebaseio.com/v0/topstories.json"
    with urllib.request.urlopen(url, timeout=10) as resp:
        story_ids = json.loads(resp.read())[:count]

    stories = []
    for sid in story_ids:
        with urllib.request.urlopen(
            f"https://hacker-news.firebaseio.com/v0/item/{sid}.json", timeout=10
        ) as resp:
            story = json.loads(resp.read())
            stories.append(f"- {story.get('title', 'No title')} ({story.get('score', 0)} pts)")

    return "\n".join(stories)


def get_timestamp() -> str:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


# ── Execute function (no LLM needed) ────────────────────────────────────


async def build_digest(ctx, tools):
    """Build a daily tech digest using tools directly."""
    timestamp_tool = tools["get_timestamp"]
    hn_tool = tools["fetch_top_hn_stories"]

    timestamp = timestamp_tool.run({})
    stories = hn_tool.run({"count": 5})

    return f"# Tech Digest\nGenerated: {timestamp}\n\n## Top Hacker News Stories\n{stories}"


# ── Create the agent ─────────────────────────────────────────────────────

agent = ToolAgent(
    name="digest-builder",
    description="Builds a daily tech digest from Hacker News",
    tools=[
        FunctionTool(fetch_top_hn_stories),
        FunctionTool(get_timestamp),
    ],
    execute=build_digest,
    output_key="digest",
)


async def main():
    ctx = Context(session_id="digest-1", cwd=os.getcwd())
    ctx.set_input("Build today's digest")

    async for event in agent.run(ctx):
        print(event.content)

    print(f"\nStored in state: {bool(ctx.state.get('digest'))}")


if __name__ == "__main__":
    asyncio.run(main())
