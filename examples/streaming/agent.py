"""Streaming agent — yields response chunks as they arrive.

Demonstrates the stream=True option for real-time output.

Usage:
    ACP_BACKEND=gemini python examples/streaming/agent.py
"""
import asyncio
import os

from acp_agent_framework import Agent, Context


agent = Agent(
    name="storyteller",
    backend=os.environ.get("ACP_BACKEND", "gemini"),
    instruction="You are a creative storyteller. Write engaging short stories.",
    stream=True,
)


async def main():
    ctx = Context(session_id="story-1", cwd=os.getcwd())
    ctx.set_input("Write a 3-paragraph story about a robot learning to paint.")

    print("Streaming response:\n")
    async for event in agent.run(ctx):
        if event.type == "stream_chunk":
            print(event.content, end="", flush=True)
        elif event.type == "message":
            pass  # final assembled message
    print()


if __name__ == "__main__":
    asyncio.run(main())
