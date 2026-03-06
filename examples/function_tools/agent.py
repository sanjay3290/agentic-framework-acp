"""Agent with FunctionTools — wraps plain Python functions as tools.

The agent can call these tools via MCP to get real data.
Demonstrates auto-schema extraction from type hints.

Usage:
    ACP_BACKEND=gemini python examples/function_tools/agent.py
"""
import asyncio
import json
import os
import sys
import urllib.request

from acp_agent_framework import Agent, Context, FunctionTool, serve


# ── Define plain Python functions ────────────────────────────────────────


def get_weather(city: str) -> str:
    """Get current weather for a city using wttr.in API."""
    try:
        url = f"https://wttr.in/{city}?format=j1"
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
            current = data["current_condition"][0]
            return (
                f"Weather in {city}: {current['weatherDesc'][0]['value']}, "
                f"{current['temp_C']}°C, humidity {current['humidity']}%, "
                f"wind {current['windspeedKmph']} km/h"
            )
    except Exception as e:
        return f"Could not fetch weather for {city}: {e}"


def calculate(expression: str) -> str:
    """Evaluate a math expression safely. Supports +, -, *, /, **, ()."""
    allowed = set("0123456789.+-*/() ")
    if not all(c in allowed for c in expression):
        return "Error: only numeric expressions with +, -, *, /, ** are allowed"
    try:
        result = eval(expression, {"__builtins__": {}})  # noqa: S307
        return str(result)
    except Exception as e:
        return f"Error: {e}"


def convert_units(value: float, from_unit: str, to_unit: str) -> str:
    """Convert between common units (km/miles, kg/lbs, C/F)."""
    conversions = {
        ("km", "miles"): lambda v: v * 0.621371,
        ("miles", "km"): lambda v: v * 1.60934,
        ("kg", "lbs"): lambda v: v * 2.20462,
        ("lbs", "kg"): lambda v: v * 0.453592,
        ("c", "f"): lambda v: v * 9 / 5 + 32,
        ("f", "c"): lambda v: (v - 32) * 5 / 9,
        ("m", "ft"): lambda v: v * 3.28084,
        ("ft", "m"): lambda v: v * 0.3048,
    }
    key = (from_unit.lower(), to_unit.lower())
    if key not in conversions:
        return f"Unknown conversion: {from_unit} -> {to_unit}"
    result = conversions[key](value)
    return f"{value} {from_unit} = {result:.2f} {to_unit}"


# ── Create the agent ─────────────────────────────────────────────────────

agent = Agent(
    name="utility-assistant",
    backend=os.environ.get("ACP_BACKEND", "gemini"),
    instruction=(
        "You are a helpful utility assistant. You have tools for weather, "
        "math calculations, and unit conversions. Use them when appropriate."
    ),
    tools=[
        FunctionTool(get_weather),
        FunctionTool(calculate),
        FunctionTool(convert_units),
    ],
)


async def one_shot(query: str) -> None:
    ctx = Context(session_id="demo", cwd=os.getcwd())
    ctx.set_input(query)
    async for event in agent.run(ctx):
        if event.type == "message":
            print(event.content)


if __name__ == "__main__":
    if "--query" in sys.argv:
        idx = sys.argv.index("--query")
        query = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "What's the weather in London?"
        asyncio.run(one_shot(query))
    else:
        serve(agent)
