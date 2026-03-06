# Agent Types Reference

This document provides comprehensive documentation for every agent type in the ACP Agent Framework. Each section covers the class interface, all configurable fields, runtime behavior, and complete runnable examples.

---

## Table of Contents

1. [BaseAgent](#1-baseagent)
2. [Agent (LLM-Backed)](#2-agent-llm-backed)
3. [SequentialAgent](#3-sequentialagent)
4. [RouterAgent](#4-routeragent)
5. [ToolAgent](#5-toolagent)
6. [Lifecycle Hooks](#6-lifecycle-hooks)
7. [Creating Custom Agents](#7-creating-custom-agents)

---

## 1. BaseAgent

`BaseAgent` is the abstract base class from which every agent in the framework inherits. It combines Pydantic's `BaseModel` for configuration validation with Python's `ABC` for enforcing the `run()` contract.

**Module:** `acp_agent_framework.agents.base`

### Class Definition

```python
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Callable, Optional
from pydantic import BaseModel, Field, field_validator
from acp_agent_framework.context import Context
from acp_agent_framework.events import Event

class BaseAgent(ABC, BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    name: str
    description: str = ""
    sub_agents: list[Any] = Field(default_factory=list)
    before_run: Optional[Callable] = Field(default=None, exclude=True)
    after_run: Optional[Callable] = Field(default=None, exclude=True)

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Agent name must not be empty")
        return v

    @abstractmethod
    async def run(self, ctx: Context) -> AsyncGenerator[Event, None]:
        yield  # type: ignore
```

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | *required* | Unique identifier for the agent. Validated to be non-empty. Appears as the `author` field on emitted `Event` objects. |
| `description` | `str` | `""` | Human-readable description of the agent's purpose. Used by the ACP server when advertising agent capabilities. |
| `sub_agents` | `list[Any]` | `[]` | List of child agents. Primarily used by composite agents (SequentialAgent, RouterAgent) but available on all agents for hierarchical organization. |
| `before_run` | `Optional[Callable]` | `None` | Async callback invoked before the agent's main logic executes. Receives a `Context` object. Excluded from Pydantic serialization. |
| `after_run` | `Optional[Callable]` | `None` | Async callback invoked after the agent's main logic completes. Receives a `Context` object. Excluded from Pydantic serialization. |

### The `run()` Method

Every agent must implement the abstract `run()` method. It is an async generator that:

- Accepts a single `Context` argument containing session state, input, and output storage.
- Yields `Event` objects as it produces results.
- May yield zero, one, or many events depending on the agent type and configuration.

### Validation

The `name` field has a Pydantic field validator that rejects empty or whitespace-only strings:

```python
from acp_agent_framework import Agent

# This raises a ValidationError:
try:
    agent = Agent(name="", backend="claude", instruction="test")
except Exception as e:
    print(e)  # "Agent name must not be empty"
```

### Pydantic Configuration

`model_config = {"arbitrary_types_allowed": True}` is set because several fields (such as `before_run`, `after_run`, and tool objects) are not standard JSON-serializable types. This setting allows Pydantic to accept them without raising type errors during model construction.

### Event Objects

All agents communicate through `Event` instances:

```python
from acp_agent_framework import Event, EventActions

event = Event(
    author="my-agent",
    type="message",
    content="Hello from the agent",
)

# Events auto-generate an id (UUID) and timestamp
print(event.id)         # e.g., "a3f1c2d4-..."
print(event.timestamp)  # e.g., 1709654321.123

# Optional actions for state changes or agent transfers
event_with_actions = Event(
    author="my-agent",
    type="message",
    content="Transferring to specialist",
    actions=EventActions(
        state_delta={"key": "value"},
        transfer_to_agent="specialist-agent",
        escalate=True,
    ),
)
```

**Event Fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | auto UUID | Unique event identifier. |
| `author` | `str` | *required* | Name of the agent that produced the event. |
| `type` | `str` | *required* | Event type: `"message"`, `"stream_chunk"`, `"tool_result"`, or custom. |
| `content` | `Any` | *required* | The event payload. Usually a string, but can be any type. |
| `timestamp` | `float` | `time.time()` | Unix timestamp of event creation. |
| `actions` | `Optional[EventActions]` | `None` | Optional actions: state deltas, agent transfers, escalation flags. |

---

## 2. Agent (LLM-Backed)

`Agent` is the primary agent type. It sends a prompt to an LLM backend via the ACP protocol, optionally bridges local tools through MCP, and supports streaming, multi-turn conversation, skills, guardrails, and state management.

**Module:** `acp_agent_framework.agents.agent`

### Class Definition

```python
class Agent(BaseAgent):
    backend: str
    instruction: Union[str, Callable] = Field(exclude=True)
    tools: list[Any] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    output_key: Optional[str] = None
    stream: bool = False
    multi_turn: bool = False
    input_guardrails: list[Any] = Field(default_factory=list)
    output_guardrails: list[Any] = Field(default_factory=list)
```

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `backend` | `str` | *required* | Name of the backend to use. Built-in options: `"claude"`, `"gemini"`, `"codex"`, `"openai"`, `"ollama"`. Custom backends can be registered via `BackendRegistry`. |
| `instruction` | `Union[str, Callable]` | *required* | The system instruction. Can be a static string or a callable that receives a `Context` object and returns a string. Dynamic instructions enable reading from state at runtime. |
| `tools` | `list[Any]` | `[]` | List of tool instances (typically `FunctionTool` or custom `BaseTool` subclasses). These are bridged to the LLM backend via an MCP server that the agent starts automatically. |
| `skills` | `list[str]` | `[]` | List of skill names to load from `.agents/skills/` directories. Skills are SKILL.md files whose instruction text is prepended to the agent's instruction. Dependencies are resolved in topological order. |
| `output_key` | `Optional[str]` | `None` | If set, the agent's response is stored in `ctx.state` under this key. Essential for chaining agents in a SequentialAgent pipeline. |
| `stream` | `bool` | `False` | When `True`, the agent yields incremental `stream_chunk` events as tokens arrive from the backend, in addition to the final `message` event. |
| `multi_turn` | `bool` | `False` | When `True`, the agent appends user input and assistant responses to `ctx.get_history()` and includes the full conversation history in subsequent prompts. |
| `input_guardrails` | `list[Any]` | `[]` | List of `Guardrail` instances applied to the assembled prompt before it is sent to the backend. Guardrails can transform the text or raise `GuardrailError` to block execution. |
| `output_guardrails` | `list[Any]` | `[]` | List of `Guardrail` instances applied to the response after it is received from the backend. Guardrails can transform or reject the output. |

### Execution Flow

When `agent.run(ctx)` is called, the following sequence occurs:

1. **before_run hook** -- If `self.before_run` is set, it is awaited with the context.
2. **MCP tool bridge** -- If `self.tools` is non-empty, an `McpBridge` is started. This spins up a local MCP server that exposes the tools to the ACP backend.
3. **Backend startup** -- The configured backend process is spawned via `AcpBackend.start()`.
4. **Session creation** -- A new ACP session is opened with `backend.new_session()`, passing the working directory and MCP server configuration.
5. **Instruction resolution** -- `resolve_instruction(ctx)` is called. If skills are configured, they are loaded and their instructions are prepended to the base instruction in dependency order.
6. **Prompt assembly** -- The instruction, conversation history (if `multi_turn`), and user input from `ctx.get_input()` are concatenated.
7. **Input guardrails** -- Each input guardrail's `validate()` method is called on the assembled prompt.
8. **LLM invocation** -- Either `backend.prompt()` (blocking) or `backend.prompt_stream()` (streaming) is called.
9. **Output guardrails** -- Each output guardrail's `validate()` method is called on the response.
10. **State updates** -- The response is stored via `ctx.set_output()`. If `output_key` is set, it is also written to `ctx.state`.
11. **History tracking** -- If `multi_turn`, the user input and assistant response are appended to the conversation history.
12. **Event emission** -- A `message` event is yielded (and `stream_chunk` events if streaming).
13. **Cleanup** -- The backend and MCP bridge are stopped in a `finally` block.
14. **after_run hook** -- If `self.after_run` is set, it is awaited with the context.

### Available Backends

The `BackendRegistry` singleton comes pre-configured with these backends:

| Name | Command | Args |
|------|---------|------|
| `"claude"` | `claude-agent-acp` | (none) |
| `"gemini"` | `gemini` | `["--acp"]` |
| `"codex"` | `npx` | `["@zed-industries/codex-acp"]` |
| `"openai"` | `openai-acp` | (none) |
| `"ollama"` | `ollama-acp` | (none) |

Register a custom backend:

```python
from acp_agent_framework import BackendRegistry, BackendConfig

registry = BackendRegistry()
registry.register("my-local-llm", BackendConfig(
    command="/usr/local/bin/my-llm-acp",
    args=["--model", "my-model"],
    env={"MY_API_KEY": "sk-..."},
    timeout=60.0,
    max_retries=2,
    retry_base_delay=0.5,
))
```

### Example: Minimal Agent

```python
from acp_agent_framework import Agent, serve

agent = Agent(
    name="simple-assistant",
    backend="claude",
    instruction="You are a helpful coding assistant. Be concise.",
)

if __name__ == "__main__":
    serve(agent)
```

### Example: Static Instruction

```python
import asyncio
from acp_agent_framework import Agent, Context

async def main():
    agent = Agent(
        name="greeter",
        backend="claude",
        instruction="You are a friendly greeter. Say hello and ask how you can help.",
    )

    ctx = Context(session_id="session-1", cwd=".")
    ctx.set_input("Hi there!")

    async for event in agent.run(ctx):
        print(f"[{event.type}] {event.content}")

asyncio.run(main())
```

### Example: Dynamic Instruction with Context

When `instruction` is a callable, it receives the `Context` object and must return a string. This allows the instruction to incorporate state values set by previous agents in a pipeline.

```python
import asyncio
from acp_agent_framework import Agent, Context, State

async def main():
    state = State(initial={"user_name": "Sanjay", "preferred_language": "Python"})

    agent = Agent(
        name="personalized-assistant",
        backend="claude",
        instruction=lambda ctx: (
            f"You are a coding assistant for {ctx.state.get('user_name')}. "
            f"They prefer {ctx.state.get('preferred_language')}. "
            f"Always provide examples in their preferred language."
        ),
    )

    ctx = Context(session_id="session-2", cwd=".", state=state)
    ctx.set_input("How do I read a file?")

    async for event in agent.run(ctx):
        print(event.content)

asyncio.run(main())
```

### Example: Tools with FunctionTool

`FunctionTool` wraps a plain Python function (sync or async) and auto-extracts its name, docstring, and parameter schema. The tools are exposed to the LLM backend via an MCP bridge, allowing the LLM to call them during inference.

```python
import asyncio
from acp_agent_framework import Agent, Context, FunctionTool

def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    # In production, call a real weather API
    return f"The weather in {city} is 72F and sunny."

def calculate(expression: str) -> str:
    """Evaluate a mathematical expression."""
    try:
        result = eval(expression)
        return str(result)
    except Exception as e:
        return f"Error: {e}"

async def fetch_url(url: str) -> str:
    """Fetch the content of a URL."""
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.text()

weather_tool = FunctionTool(get_weather)
calc_tool = FunctionTool(calculate)
fetch_tool = FunctionTool(fetch_url)  # async functions work too

async def main():
    agent = Agent(
        name="tool-user",
        backend="claude",
        instruction=(
            "You are an assistant with access to tools. "
            "Use get_weather to check weather, calculate for math, "
            "and fetch_url to retrieve web pages."
        ),
        tools=[weather_tool, calc_tool, fetch_tool],
    )

    ctx = Context(session_id="tool-session", cwd=".")
    ctx.set_input("What is the weather in San Francisco and what is 42 * 17?")

    async for event in agent.run(ctx):
        print(f"[{event.type}] {event.content}")

asyncio.run(main())
```

**FunctionTool details:**

| Method | Description |
|--------|-------------|
| `run(args)` | Synchronous execution. Raises `TypeError` if the wrapped function is async. |
| `arun(args)` | Async execution. Awaits async functions; runs sync functions directly. |
| `get_schema()` | Returns a dict with `name`, `description`, and `parameters` extracted from the function signature. |

### Example: Skills

Skills are reusable instruction fragments stored as `SKILL.md` files. They follow the agentskills.io spec and are loaded from two locations (in priority order):

1. **Project-level:** `.agents/skills/<skill-name>/SKILL.md` (relative to `ctx.cwd`)
2. **User-level:** `~/.agents/skills/<skill-name>/SKILL.md`

A SKILL.md file can have optional YAML frontmatter:

```markdown
---
name: code-review
description: Performs thorough code reviews
dependencies:
  - coding-standards
---

When reviewing code, check for:
- Logic errors and edge cases
- Security vulnerabilities
- Performance issues
- Adherence to coding standards
- Test coverage gaps
```

When an agent loads skills, their instructions are prepended to the agent's own instruction in topological order (dependencies first).

```python
import asyncio
from acp_agent_framework import Agent, Context

async def main():
    agent = Agent(
        name="reviewer",
        backend="claude",
        instruction="Review the code provided by the user.",
        skills=["code-review"],
    )

    ctx = Context(session_id="review-1", cwd="/path/to/project")
    ctx.set_input("Please review this pull request: ...")

    async for event in agent.run(ctx):
        print(event.content)

asyncio.run(main())
```

### Example: output_key for State Storage

The `output_key` field writes the agent's response into `ctx.state` under the given key. This is the primary mechanism for passing data between agents in a `SequentialAgent` pipeline.

```python
import asyncio
from acp_agent_framework import Agent, Context

async def main():
    agent = Agent(
        name="analyzer",
        backend="claude",
        instruction="Analyze the given code and list all functions.",
        output_key="analysis_result",
    )

    ctx = Context(session_id="s1", cwd=".")
    ctx.set_input("def foo(): pass\ndef bar(): pass")

    async for event in agent.run(ctx):
        pass  # consume events

    # The response is now available in state
    print(ctx.state.get("analysis_result"))

asyncio.run(main())
```

### Example: Streaming

When `stream=True`, the agent yields `stream_chunk` events as each token arrives from the backend, followed by a final `message` event with the complete response.

```python
import asyncio
from acp_agent_framework import Agent, Context

async def main():
    agent = Agent(
        name="streaming-agent",
        backend="claude",
        instruction="Write a short poem about programming.",
        stream=True,
    )

    ctx = Context(session_id="stream-1", cwd=".")
    ctx.set_input("Write a haiku about Python")

    async for event in agent.run(ctx):
        if event.type == "stream_chunk":
            print(event.content, end="", flush=True)
        elif event.type == "message":
            print("\n--- Complete response stored ---")

asyncio.run(main())
```

### Example: Multi-Turn Conversation

When `multi_turn=True`, the agent tracks conversation history in the context. Each call to `run()` includes the full history in the prompt, and appends the new user/assistant exchange afterward.

```python
import asyncio
from acp_agent_framework import Agent, Context

async def main():
    agent = Agent(
        name="chat-agent",
        backend="claude",
        instruction="You are a helpful assistant. Remember previous messages.",
        multi_turn=True,
    )

    ctx = Context(session_id="chat-1", cwd=".")

    # Turn 1
    ctx.set_input("My name is Sanjay.")
    async for event in agent.run(ctx):
        print(f"Assistant: {event.content}")

    # Turn 2 -- the agent remembers the previous exchange
    ctx.set_input("What is my name?")
    async for event in agent.run(ctx):
        print(f"Assistant: {event.content}")

    # Inspect full history
    for msg in ctx.get_history():
        print(f"  {msg['role']}: {msg['content'][:80]}...")

asyncio.run(main())
```

### Example: Input and Output Guardrails

Guardrails are validation functions applied before the prompt is sent (input guardrails) or after the response is received (output guardrails). A guardrail function receives a string and either:

- Returns `None` to pass the text through unchanged.
- Returns a modified string to transform the text.
- Raises `GuardrailError` to block execution entirely.

```python
import asyncio
from acp_agent_framework import Agent, Context, Guardrail, GuardrailError

def block_profanity(text: str):
    """Block prompts containing profanity."""
    banned_words = ["badword1", "badword2"]
    for word in banned_words:
        if word in text.lower():
            raise GuardrailError(
                f"Input contains banned word: {word}",
                guardrail_name="profanity-filter",
            )
    return None  # pass through unchanged

def enforce_max_length(text: str):
    """Truncate responses longer than 500 characters."""
    if len(text) > 500:
        return text[:500] + "..."
    return None  # pass through unchanged

def redact_emails(text: str):
    """Redact email addresses from the response."""
    import re
    redacted = re.sub(r'\S+@\S+\.\S+', '[REDACTED]', text)
    if redacted != text:
        return redacted
    return None

async def main():
    agent = Agent(
        name="guarded-agent",
        backend="claude",
        instruction="You are a helpful assistant.",
        input_guardrails=[
            Guardrail(name="profanity-filter", fn=block_profanity),
        ],
        output_guardrails=[
            Guardrail(name="length-limiter", fn=enforce_max_length),
            Guardrail(name="email-redactor", fn=redact_emails),
        ],
    )

    ctx = Context(session_id="guarded-1", cwd=".")
    ctx.set_input("Tell me about email security for user@example.com")

    try:
        async for event in agent.run(ctx):
            print(event.content)
    except GuardrailError as e:
        print(f"Blocked by guardrail '{e.guardrail_name}': {e}")

asyncio.run(main())
```

---

## 3. SequentialAgent

`SequentialAgent` runs a list of agents in order. After each agent completes, its output is stored in the context as a named agent output. Subsequent agents can read previous outputs from state via `output_key` or from `ctx.get_agent_output()`.

**Module:** `acp_agent_framework.agents.sequential`

### Class Definition

```python
class SequentialAgent(BaseAgent):
    agents: list[BaseAgent] = Field(default_factory=list)

    async def run(self, ctx: Context) -> AsyncGenerator[Event, None]:
        if self.before_run:
            await self.before_run(ctx)
        for agent in self.agents:
            async for event in agent.run(ctx):
                yield event
            output = ctx.get_output()
            if output is not None:
                ctx.set_agent_output(agent.name, output)
        if self.after_run:
            await self.after_run(ctx)
```

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `agents` | `list[BaseAgent]` | `[]` | Ordered list of agents to execute. Each agent runs to completion before the next begins. |

All `BaseAgent` fields (`name`, `description`, `sub_agents`, `before_run`, `after_run`) are also available.

### How Data Flows Between Agents

The SequentialAgent uses two mechanisms to pass data along the pipeline:

1. **`output_key` on child agents** -- When a child agent has `output_key="some_key"`, its response is stored in `ctx.state.set("some_key", response)`. The next agent can read it via `ctx.state.get("some_key")` inside a dynamic instruction.

2. **`ctx.set_agent_output()`** -- After each agent runs, the SequentialAgent calls `ctx.set_agent_output(agent.name, output)`. Any agent (or external code) can retrieve it with `ctx.get_agent_output("agent-name")`.

### Example: Research Pipeline

```python
import asyncio
from acp_agent_framework import Agent, SequentialAgent, Context, serve

researcher = Agent(
    name="researcher",
    backend="claude",
    instruction="Research the given topic thoroughly. Provide detailed findings.",
    output_key="research",
)

summarizer = Agent(
    name="summarizer",
    backend="claude",
    instruction=lambda ctx: (
        f"Summarize this research concisely:\n\n{ctx.state.get('research', '')}"
    ),
    output_key="summary",
)

formatter = Agent(
    name="formatter",
    backend="claude",
    instruction=lambda ctx: (
        f"Format this summary as a professional report with headers:\n\n"
        f"{ctx.state.get('summary', '')}"
    ),
)

pipeline = SequentialAgent(
    name="research-pipeline",
    description="Research, summarize, and format a topic",
    agents=[researcher, summarizer, formatter],
)

# Option 1: Serve as ACP agent
if __name__ == "__main__":
    serve(pipeline)
```

### Example: Running Programmatically and Inspecting State

```python
import asyncio
from acp_agent_framework import Agent, SequentialAgent, Context, State

async def main():
    extractor = Agent(
        name="extractor",
        backend="claude",
        instruction="Extract all person names from the text. Return them as a comma-separated list.",
        output_key="names",
    )

    categorizer = Agent(
        name="categorizer",
        backend="claude",
        instruction=lambda ctx: (
            f"Categorize these names by likely nationality:\n\n"
            f"{ctx.state.get('names', '')}"
        ),
        output_key="categorized",
    )

    pipeline = SequentialAgent(
        name="name-pipeline",
        agents=[extractor, categorizer],
    )

    ctx = Context(session_id="pipe-1", cwd=".")
    ctx.set_input("The meeting was attended by Sanjay Patel, Yuki Tanaka, and Maria Garcia.")

    async for event in pipeline.run(ctx):
        print(f"[{event.author}] {event.content[:100]}...")

    # After the pipeline, inspect all intermediate results
    print("\n--- State ---")
    print(f"names: {ctx.state.get('names')}")
    print(f"categorized: {ctx.state.get('categorized')}")

    # Or access by agent name
    print(f"\nextractor output: {ctx.get_agent_output('extractor')}")
    print(f"categorizer output: {ctx.get_agent_output('categorizer')}")

asyncio.run(main())
```

### Example: Mixing Agent Types in a Pipeline

A SequentialAgent can contain any `BaseAgent` subclass, not just `Agent`. You can mix ToolAgents, custom agents, and LLM-backed agents in a single pipeline.

```python
import asyncio
from acp_agent_framework import Agent, ToolAgent, SequentialAgent, Context, FunctionTool

def load_file(path: str) -> str:
    """Load file contents from disk."""
    with open(path) as f:
        return f.read()

file_tool = FunctionTool(load_file)

async def read_source(ctx, tools_dict):
    """Use the load_file tool to read a source file."""
    path = ctx.get_input()
    result = tools_dict["load_file"].run({"path": path})
    return result

loader = ToolAgent(
    name="file-loader",
    tools=[file_tool],
    execute=read_source,
    output_key="source_code",
)

reviewer = Agent(
    name="code-reviewer",
    backend="claude",
    instruction=lambda ctx: (
        f"Review this code for bugs and improvements:\n\n"
        f"```\n{ctx.state.get('source_code', '')}\n```"
    ),
)

pipeline = SequentialAgent(
    name="review-pipeline",
    agents=[loader, reviewer],
)

async def main():
    ctx = Context(session_id="review-1", cwd=".")
    ctx.set_input("/path/to/source.py")

    async for event in pipeline.run(ctx):
        print(f"[{event.author}] {event.content}")

asyncio.run(main())
```

---

## 4. RouterAgent

`RouterAgent` examines the user's input and routes it to a specialist agent based on keyword matching. It performs case-insensitive substring matching against each route's keyword list and delegates to the first matching agent.

**Module:** `acp_agent_framework.agents.router`

### Class Definitions

```python
class Route(BaseModel):
    model_config = {"arbitrary_types_allowed": True}
    keywords: list[str]
    agent: BaseAgent

class RouterAgent(BaseAgent):
    routes: list[Route] = Field(default_factory=list)
    default_agent: Optional[BaseAgent] = None
```

### Fields

**Route:**

| Field | Type | Description |
|-------|------|-------------|
| `keywords` | `list[str]` | List of keywords. If any keyword appears (case-insensitive substring match) in the user input, this route is selected. |
| `agent` | `BaseAgent` | The agent to delegate to when this route matches. |

**RouterAgent:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `routes` | `list[Route]` | `[]` | Ordered list of routes. The first matching route wins. |
| `default_agent` | `Optional[BaseAgent]` | `None` | Fallback agent used when no route matches. If `None` and no route matches, the router yields a "No matching route found" message event. |

### Routing Logic

The `_find_route()` method iterates through routes in order:

```python
def _find_route(self, text: str) -> Optional[BaseAgent]:
    text_lower = text.lower()
    for route in self.routes:
        if any(kw.lower() in text_lower for kw in route.keywords):
            return route.agent
    return self.default_agent
```

Key behaviors:

- Matching is case-insensitive.
- Matching is substring-based: the keyword `"python"` matches `"How do I learn Python?"`.
- Routes are evaluated in order; the first match wins.
- If no route matches and no `default_agent` is set, an event with content `"No matching route found for input."` is yielded.

### Example: Multi-Domain Router

```python
import asyncio
from acp_agent_framework import Agent, Route, RouterAgent, Context, serve

code_agent = Agent(
    name="code-expert",
    backend="claude",
    instruction="You are a coding expert. Help with code questions, debugging, and best practices.",
)

writing_agent = Agent(
    name="writing-expert",
    backend="claude",
    instruction="You are a writing expert. Help with essays, emails, and content creation.",
)

math_agent = Agent(
    name="math-expert",
    backend="claude",
    instruction="You are a math expert. Help with calculations, equations, and mathematical concepts.",
)

router = RouterAgent(
    name="smart-router",
    description="Routes questions to the right specialist",
    routes=[
        Route(
            keywords=["code", "python", "javascript", "bug", "function", "api"],
            agent=code_agent,
        ),
        Route(
            keywords=["write", "essay", "email", "blog", "content", "grammar"],
            agent=writing_agent,
        ),
        Route(
            keywords=["math", "calculate", "equation", "number", "algebra"],
            agent=math_agent,
        ),
    ],
    default_agent=code_agent,
)

if __name__ == "__main__":
    serve(router)
```

### Example: Router with Default Fallback

```python
import asyncio
from acp_agent_framework import Agent, Route, RouterAgent, Context

async def main():
    general_agent = Agent(
        name="general",
        backend="claude",
        instruction="You are a general-purpose assistant.",
    )

    devops_agent = Agent(
        name="devops-expert",
        backend="claude",
        instruction="You are a DevOps expert specializing in Docker, Kubernetes, and CI/CD.",
    )

    router = RouterAgent(
        name="helpdesk-router",
        routes=[
            Route(
                keywords=["docker", "kubernetes", "k8s", "ci/cd", "pipeline", "terraform", "deploy"],
                agent=devops_agent,
            ),
        ],
        default_agent=general_agent,
    )

    # This matches "docker" -> routes to devops-expert
    ctx = Context(session_id="r1", cwd=".")
    ctx.set_input("How do I build a multi-stage Docker image?")
    async for event in router.run(ctx):
        print(f"[{event.author}] {event.content}")

    # This matches nothing -> routes to general agent (default)
    ctx2 = Context(session_id="r2", cwd=".")
    ctx2.set_input("What is the capital of France?")
    async for event in router.run(ctx2):
        print(f"[{event.author}] {event.content}")

asyncio.run(main())
```

### Example: Router Without Default

When no default is set and no route matches, the router produces its own event:

```python
import asyncio
from acp_agent_framework import Route, RouterAgent, Context, Agent

async def main():
    router = RouterAgent(
        name="strict-router",
        routes=[
            Route(keywords=["python"], agent=Agent(
                name="python-agent", backend="claude", instruction="Python expert."
            )),
        ],
        # No default_agent
    )

    ctx = Context(session_id="r3", cwd=".")
    ctx.set_input("Tell me about Rust")

    async for event in router.run(ctx):
        print(f"[{event.author}] {event.content}")
        # Output: [strict-router] No matching route found for input.

asyncio.run(main())
```

---

## 5. ToolAgent

`ToolAgent` executes tools directly without an LLM backend. You provide an async `execute` function that receives the context and a dictionary of tools, calls them as needed, and returns a result string.

This is useful for deterministic operations like file I/O, API calls, database queries, or any task where you do not need LLM reasoning.

**Module:** `acp_agent_framework.agents.tool_agent`

### Class Definition

```python
class ToolAgent(BaseAgent):
    tools: list[Any] = Field(default_factory=list)
    execute: Callable = Field(exclude=True)
    output_key: Optional[str] = None
```

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `tools` | `list[Any]` | `[]` | List of tool instances (typically `FunctionTool`). These are indexed by name into a dict passed to the `execute` function. |
| `execute` | `Callable` | *required* | An async function with signature `async def execute(ctx: Context, tools_dict: dict[str, BaseTool]) -> str`. It receives the context and a dictionary mapping tool names to tool objects. It must return the result as a string (or any value that can be `str()`-ed). |
| `output_key` | `Optional[str]` | `None` | If set, the result is stored in `ctx.state` under this key. |

### Execution Flow

1. **before_run hook** -- If set, awaited with context.
2. **Tools indexing** -- `tools_dict = {tool.name: tool for tool in self.tools}` creates a name-keyed dictionary.
3. **Execute** -- The `execute` function is awaited with `(ctx, tools_dict)`.
4. **Result storage** -- The result is converted to a string, stored via `ctx.set_output()`, and optionally written to state via `output_key`.
5. **Event emission** -- A single `tool_result` event is yielded.
6. **after_run hook** -- If set, awaited with context.

### Example: File Operations Agent

```python
import asyncio
from acp_agent_framework import ToolAgent, Context, FunctionTool

def read_file(path: str) -> str:
    """Read a file and return its contents."""
    with open(path) as f:
        return f.read()

def write_file(path: str, content: str) -> str:
    """Write content to a file."""
    with open(path, "w") as f:
        f.write(content)
    return f"Written {len(content)} bytes to {path}"

def count_lines(text: str) -> str:
    """Count lines in text."""
    return str(len(text.splitlines()))

async def process_file(ctx, tools_dict):
    """Read a file, count its lines, and write a report."""
    path = ctx.get_input()
    content = tools_dict["read_file"].run({"path": path})
    line_count = tools_dict["count_lines"].run({"text": content})
    report = f"File: {path}\nLines: {line_count}\nSize: {len(content)} bytes"
    tools_dict["write_file"].run({"path": f"{path}.report", "content": report})
    return report

async def main():
    agent = ToolAgent(
        name="file-processor",
        tools=[
            FunctionTool(read_file),
            FunctionTool(write_file),
            FunctionTool(count_lines),
        ],
        execute=process_file,
        output_key="file_report",
    )

    ctx = Context(session_id="tool-1", cwd=".")
    ctx.set_input("/tmp/example.txt")

    async for event in agent.run(ctx):
        print(f"[{event.type}] {event.content}")

    # Result is also in state
    print(f"State: {ctx.state.get('file_report')}")

asyncio.run(main())
```

### Example: ToolAgent Without Tools

The `tools` list is optional. You can use a ToolAgent purely for its deterministic execution, without any tool objects:

```python
import asyncio
from acp_agent_framework import ToolAgent, Context

async def timestamp_generator(ctx, tools_dict):
    """Generate a formatted timestamp."""
    from datetime import datetime
    return datetime.now().isoformat()

async def main():
    agent = ToolAgent(
        name="timestamper",
        execute=timestamp_generator,
        output_key="timestamp",
    )

    ctx = Context(session_id="ts-1", cwd=".")

    async for event in agent.run(ctx):
        print(f"Timestamp: {event.content}")

asyncio.run(main())
```

### Example: HTTP API Call

```python
import asyncio
from acp_agent_framework import ToolAgent, Context

async def call_api(ctx, tools_dict):
    """Fetch data from an external API."""
    import aiohttp
    url = ctx.get_input()
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            return str(data)

async def main():
    agent = ToolAgent(
        name="api-caller",
        execute=call_api,
        output_key="api_response",
    )

    ctx = Context(session_id="api-1", cwd=".")
    ctx.set_input("https://api.example.com/data")

    async for event in agent.run(ctx):
        print(event.content)

asyncio.run(main())
```

---

## 6. Lifecycle Hooks

All agents (any `BaseAgent` subclass) support `before_run` and `after_run` async callbacks. These hooks run before and after the agent's main logic, respectively. They receive the `Context` object and can modify state, log information, validate preconditions, or perform cleanup.

### Hook Signatures

```python
async def before_run_hook(ctx: Context) -> None:
    ...

async def after_run_hook(ctx: Context) -> None:
    ...
```

Both hooks must be async functions that accept a single `Context` argument and return `None`.

### Example: Logging and Timing

```python
import asyncio
import time
from acp_agent_framework import Agent, Context

async def log_start(ctx: Context):
    start_time = time.time()
    ctx.state.set("temp:start_time", start_time)
    print(f"[{time.strftime('%H:%M:%S')}] Agent starting...")
    print(f"  Session: {ctx.session_id}")
    print(f"  Input: {ctx.get_input()}")

async def log_end(ctx: Context):
    start_time = ctx.state.get("temp:start_time", 0)
    elapsed = time.time() - start_time
    print(f"[{time.strftime('%H:%M:%S')}] Agent finished in {elapsed:.2f}s")
    print(f"  Output length: {len(ctx.get_output() or '')}")

async def main():
    agent = Agent(
        name="timed-agent",
        backend="claude",
        instruction="You are a helpful assistant.",
        before_run=log_start,
        after_run=log_end,
    )

    ctx = Context(session_id="hook-1", cwd=".")
    ctx.set_input("Explain the difference between threads and processes.")

    async for event in agent.run(ctx):
        print(event.content)

asyncio.run(main())
```

Note: State keys prefixed with `temp:` are excluded by `State.get_persistable()`, making them suitable for ephemeral metadata like timing values.

### Example: Validation in before_run

```python
import asyncio
from acp_agent_framework import Agent, Context

async def require_input(ctx: Context):
    """Ensure the context has non-empty input before running."""
    user_input = ctx.get_input()
    if not user_input or not user_input.strip():
        raise ValueError("Agent requires non-empty input")

async def main():
    agent = Agent(
        name="strict-agent",
        backend="claude",
        instruction="Answer the question.",
        before_run=require_input,
    )

    ctx = Context(session_id="v1", cwd=".")
    ctx.set_input("")  # Empty input

    try:
        async for event in agent.run(ctx):
            print(event.content)
    except ValueError as e:
        print(f"Validation failed: {e}")

asyncio.run(main())
```

### Example: Cleanup in after_run

```python
import asyncio
from acp_agent_framework import ToolAgent, Context

async def cleanup_temp_files(ctx: Context):
    """Remove temporary files created during execution."""
    import os
    temp_files = ctx.state.get("temp:files_created", [])
    for path in temp_files:
        if os.path.exists(path):
            os.remove(path)
            print(f"Cleaned up: {path}")

async def create_report(ctx, tools_dict):
    """Generate a report and track temp files."""
    import tempfile
    report = f"Report for: {ctx.get_input()}"
    fd, path = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w") as f:
        f.write(report)
    ctx.state.set("temp:files_created", [path])
    return report

import os

async def main():
    agent = ToolAgent(
        name="reporting-agent",
        execute=create_report,
        after_run=cleanup_temp_files,
    )

    ctx = Context(session_id="c1", cwd=".")
    ctx.set_input("Q4 Sales Data")

    async for event in agent.run(ctx):
        print(event.content)

asyncio.run(main())
```

### Hooks on Composite Agents

Lifecycle hooks work on SequentialAgent and RouterAgent as well. The parent's `before_run` fires before any child agent runs, and `after_run` fires after all children complete. Each child agent also has its own independent hooks.

```python
import asyncio
from acp_agent_framework import Agent, SequentialAgent, Context

async def pipeline_start(ctx):
    print("Pipeline starting")

async def pipeline_end(ctx):
    print("Pipeline complete")

async def step_start(ctx):
    print(f"  Step starting")

pipeline = SequentialAgent(
    name="hooked-pipeline",
    agents=[
        Agent(
            name="step-1",
            backend="claude",
            instruction="Say hello.",
            output_key="greeting",
            before_run=step_start,
        ),
        Agent(
            name="step-2",
            backend="claude",
            instruction=lambda ctx: f"Expand on: {ctx.state.get('greeting', '')}",
        ),
    ],
    before_run=pipeline_start,
    after_run=pipeline_end,
)
```

Execution order: `pipeline_start` -> `step_start` -> step-1 runs -> step-2 runs -> `pipeline_end`.

---

## 7. Creating Custom Agents

To create a custom agent, subclass `BaseAgent` and implement the async `run()` generator method. Your implementation must yield `Event` objects and can optionally call `before_run`/`after_run` hooks.

### Minimum Requirements

1. Subclass `BaseAgent`.
2. Implement `async def run(self, ctx: Context) -> AsyncGenerator[Event, None]`.
3. Yield one or more `Event` objects.

### Example: Retry Agent

An agent that retries a child agent up to N times on failure:

```python
import asyncio
from typing import AsyncGenerator
from pydantic import Field
from acp_agent_framework import BaseAgent, Context, Event

class RetryAgent(BaseAgent):
    """Wraps a child agent and retries on exception."""
    child: BaseAgent
    max_retries: int = 3

    async def run(self, ctx: Context) -> AsyncGenerator[Event, None]:
        if self.before_run:
            await self.before_run(ctx)

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                async for event in self.child.run(ctx):
                    yield event
                # If we get here without error, success
                last_error = None
                break
            except Exception as e:
                last_error = e
                yield Event(
                    author=self.name,
                    type="message",
                    content=f"Attempt {attempt}/{self.max_retries} failed: {e}",
                )

        if last_error is not None:
            yield Event(
                author=self.name,
                type="message",
                content=f"All {self.max_retries} attempts failed. Last error: {last_error}",
            )

        if self.after_run:
            await self.after_run(ctx)

# Usage
from acp_agent_framework import Agent

flaky_agent = Agent(
    name="flaky-service",
    backend="claude",
    instruction="Call the flaky external service.",
)

resilient = RetryAgent(
    name="resilient-caller",
    child=flaky_agent,
    max_retries=3,
)
```

### Example: Parallel Agent

An agent that runs multiple child agents concurrently and collects all events:

```python
import asyncio
from typing import AsyncGenerator, Any
from pydantic import Field
from acp_agent_framework import BaseAgent, Context, Event

class ParallelAgent(BaseAgent):
    """Runs multiple agents concurrently and yields all events."""
    agents: list[BaseAgent] = Field(default_factory=list)

    async def run(self, ctx: Context) -> AsyncGenerator[Event, None]:
        if self.before_run:
            await self.before_run(ctx)

        # Collect events from all agents concurrently
        async def collect_events(agent: BaseAgent) -> list[Event]:
            events = []
            async for event in agent.run(ctx):
                events.append(event)
            return events

        tasks = [collect_events(agent) for agent in self.agents]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                yield Event(
                    author=self.name,
                    type="message",
                    content=f"Agent failed: {result}",
                )
            else:
                for event in result:
                    yield event

        if self.after_run:
            await self.after_run(ctx)

# Usage
from acp_agent_framework import Agent

parallel = ParallelAgent(
    name="parallel-research",
    agents=[
        Agent(name="researcher-1", backend="claude", instruction="Research topic A.", output_key="topic_a"),
        Agent(name="researcher-2", backend="gemini", instruction="Research topic B.", output_key="topic_b"),
        Agent(name="researcher-3", backend="claude", instruction="Research topic C.", output_key="topic_c"),
    ],
)
```

### Example: Conditional Agent

An agent that chooses between two child agents based on a state condition:

```python
import asyncio
from typing import AsyncGenerator, Callable
from pydantic import Field
from acp_agent_framework import BaseAgent, Context, Event

class ConditionalAgent(BaseAgent):
    """Routes to one of two agents based on a condition function."""
    condition: Callable[[Context], bool] = Field(exclude=True)
    if_true: BaseAgent
    if_false: BaseAgent

    async def run(self, ctx: Context) -> AsyncGenerator[Event, None]:
        if self.before_run:
            await self.before_run(ctx)

        target = self.if_true if self.condition(ctx) else self.if_false

        yield Event(
            author=self.name,
            type="message",
            content=f"Condition evaluated, routing to: {target.name}",
        )

        async for event in target.run(ctx):
            yield event

        if self.after_run:
            await self.after_run(ctx)

# Usage
from acp_agent_framework import Agent

detailed_agent = Agent(
    name="detailed-responder",
    backend="claude",
    instruction="Provide a very detailed, thorough response.",
)

brief_agent = Agent(
    name="brief-responder",
    backend="claude",
    instruction="Provide a brief, concise response.",
)

conditional = ConditionalAgent(
    name="smart-responder",
    condition=lambda ctx: ctx.state.get("detail_level") == "high",
    if_true=detailed_agent,
    if_false=brief_agent,
)
```

### Example: Accumulator Agent

An agent that runs a child agent in a loop, accumulating results until a condition is met:

```python
import asyncio
from typing import AsyncGenerator, Callable
from pydantic import Field
from acp_agent_framework import BaseAgent, Context, Event

class AccumulatorAgent(BaseAgent):
    """Runs a child agent repeatedly, accumulating output until done."""
    child: BaseAgent
    max_iterations: int = 5
    stop_condition: Callable[[str], bool] = Field(exclude=True)

    async def run(self, ctx: Context) -> AsyncGenerator[Event, None]:
        if self.before_run:
            await self.before_run(ctx)

        accumulated = []

        for i in range(self.max_iterations):
            # Set current accumulated text as state
            ctx.state.set("accumulated", "\n".join(accumulated))

            async for event in self.child.run(ctx):
                yield event

            output = ctx.get_output()
            if output:
                accumulated.append(output)

            if self.stop_condition(output or ""):
                yield Event(
                    author=self.name,
                    type="message",
                    content=f"Stop condition met after {i + 1} iterations.",
                )
                break

        ctx.state.set("final_accumulated", "\n".join(accumulated))

        if self.after_run:
            await self.after_run(ctx)

# Usage
from acp_agent_framework import Agent

writer = Agent(
    name="chapter-writer",
    backend="claude",
    instruction=lambda ctx: (
        f"Continue writing the next chapter. "
        f"Previous chapters:\n{ctx.state.get('accumulated', 'None yet')}\n\n"
        f"Write 'THE END' when the story is complete."
    ),
)

story_builder = AccumulatorAgent(
    name="story-builder",
    child=writer,
    max_iterations=10,
    stop_condition=lambda text: "THE END" in text,
)
```

---

## Appendix: Context API Reference

The `Context` object is passed to every agent's `run()` method and provides session state, input/output management, and conversation history.

```python
class Context:
    def __init__(self, session_id: str, cwd: str, state: Optional[State] = None): ...
```

| Method | Signature | Description |
|--------|-----------|-------------|
| `get_input()` | `() -> Any` | Returns the current input value. |
| `set_input(value)` | `(Any) -> None` | Sets the input value. |
| `get_output()` | `() -> Any` | Returns the current output value. |
| `set_output(value)` | `(Any) -> None` | Sets the output value. |
| `set_agent_output(name, output)` | `(str, Any) -> None` | Stores output keyed by agent name. Used by SequentialAgent. |
| `get_agent_output(name)` | `(str) -> Optional[Any]` | Retrieves a named agent's output. |
| `add_message(role, content)` | `(str, str) -> None` | Appends to conversation history. Used by multi-turn agents. |
| `get_history()` | `() -> list[dict[str, str]]` | Returns conversation history as a list of `{"role": ..., "content": ...}` dicts. |
| `clear_history()` | `() -> None` | Clears conversation history. |

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `session_id` | `str` | Unique session identifier. |
| `cwd` | `str` | Working directory for the session. Used for skill loading and file operations. |
| `state` | `State` | Key-value state store with delta tracking. Keys prefixed with `temp:` are excluded from persistence. |

## Appendix: State API Reference

```python
class State:
    def __init__(self, initial: Optional[dict[str, Any]] = None): ...
```

| Method | Signature | Description |
|--------|-----------|-------------|
| `get(key, default=None)` | `(str, Any) -> Any` | Get a value. Checks delta first, then base data. |
| `set(key, value)` | `(str, Any) -> None` | Set a value in both base data and delta. |
| `get_delta()` | `() -> dict` | Returns all changes since last `commit()`. |
| `commit()` | `() -> None` | Clears the delta tracker. |
| `get_persistable()` | `() -> dict` | Returns all data excluding keys starting with `temp:`. |
| `to_dict()` | `() -> dict` | Returns the full state as a plain dict. |
