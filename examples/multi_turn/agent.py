"""Multi-turn conversational agent with memory.

The agent maintains conversation history across multiple prompts,
enabling follow-up questions and contextual responses.

Usage:
    python examples/multi_turn/agent.py
"""
import asyncio
import os

from acp_agent_framework import Agent, Context


agent = Agent(
    name="tutor",
    backend=os.environ.get("ACP_BACKEND", "gemini"),
    instruction=(
        "You are a friendly programming tutor. Explain concepts clearly "
        "with examples. Remember what the student asked before and build "
        "on previous explanations. Keep answers under 100 words."
    ),
    multi_turn=True,
)


async def main():
    ctx = Context(session_id="lesson-1", cwd=os.getcwd())

    questions = [
        "What is a Python list?",
        "How do I add items to one?",
        "What about removing items?",
    ]

    for question in questions:
        print(f"\nStudent: {question}")
        ctx.set_input(question)
        async for event in agent.run(ctx):
            if event.type == "message":
                print(f"Tutor: {event.content}")

    print(f"\nConversation history: {len(ctx.get_history())} messages")


if __name__ == "__main__":
    asyncio.run(main())
