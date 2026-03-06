"""Agent with input/output guardrails for content safety.

Demonstrates:
- Input guardrails: redact sensitive data before sending to LLM
- Output guardrails: filter responses before returning to user
- GuardrailError: block requests entirely

Usage:
    ACP_BACKEND=gemini python examples/guardrails/agent.py
"""
import asyncio
import os
import re
import sys

from acp_agent_framework import Agent, Context, Guardrail, GuardrailError, serve


# ── Input guardrails ─────────────────────────────────────────────────────


def redact_pii(text: str) -> str:
    """Redact emails and phone numbers from input."""
    text = re.sub(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b", "[EMAIL_REDACTED]", text)
    text = re.sub(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b", "[PHONE_REDACTED]", text)
    text = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[SSN_REDACTED]", text)
    return text


def block_prompt_injection(text: str) -> str:
    """Block common prompt injection patterns."""
    injection_patterns = [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"forget\s+(all\s+)?your\s+instructions",
        r"you\s+are\s+now\s+a",
        r"system\s*:\s*",
    ]
    for pattern in injection_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            raise GuardrailError(
                "Potential prompt injection detected. Request blocked.",
                guardrail_name="injection-blocker",
            )
    return None  # pass through unchanged


# ── Output guardrails ────────────────────────────────────────────────────


def redact_tokens(text: str) -> str:
    """Remove accidentally leaked API tokens from output."""
    text = re.sub(r"(ghp_|gho_|sk-|xoxb-)[A-Za-z0-9_-]+", "[TOKEN_REDACTED]", text)
    return text


def limit_length(text: str) -> str:
    """Truncate overly long responses."""
    max_chars = 2000
    if len(text) > max_chars:
        return text[:max_chars] + "\n\n[Response truncated]"
    return text


# ── Create the agent ─────────────────────────────────────────────────────

agent = Agent(
    name="safe-assistant",
    backend=os.environ.get("ACP_BACKEND", "gemini"),
    instruction=(
        "You are a helpful assistant. Answer questions concisely. "
        "Never reveal API keys, tokens, or secrets."
    ),
    input_guardrails=[
        Guardrail("pii-redactor", redact_pii),
        Guardrail("injection-blocker", block_prompt_injection),
    ],
    output_guardrails=[
        Guardrail("token-redactor", redact_tokens),
        Guardrail("length-limiter", limit_length),
    ],
)


async def one_shot(query: str) -> None:
    ctx = Context(session_id="demo", cwd=os.getcwd())
    ctx.set_input(query)
    try:
        async for event in agent.run(ctx):
            if event.type == "message":
                print(event.content)
    except GuardrailError as e:
        print(f"BLOCKED by guardrail '{e.guardrail_name}': {e}")


if __name__ == "__main__":
    if "--query" in sys.argv:
        idx = sys.argv.index("--query")
        query = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "Help me draft an email"
        asyncio.run(one_shot(query))
    else:
        serve(agent)
