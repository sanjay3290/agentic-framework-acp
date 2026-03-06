# Getting Started with ACP Agent Framework

This guide walks you through everything you need to build, run, and serve your first ACP-compatible agent using the ACP Agent Framework. By the end, you will understand the core concepts, have a working agent, and know how to expose it over both ACP stdio and HTTP.

---

## Table of Contents

1. [What is ACP Agent Framework?](#what-is-acp-agent-framework)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Your First Agent](#your-first-agent)
5. [Using the CLI](#using-the-cli)
6. [Understanding Context](#understanding-context)
7. [Adding Tools to Your Agent](#adding-tools-to-your-agent)
8. [Multi-Turn Conversations](#multi-turn-conversations)
9. [Streaming Responses](#streaming-responses)
10. [Session Persistence](#session-persistence)
11. [Next Steps](#next-steps)

---

## What is ACP Agent Framework?

ACP Agent Framework is the first open-source Python framework for building agents that are compatible with the **Agent Client Protocol (ACP)**.

### What is ACP?

ACP stands for **Agent Client Protocol**. It is a JSON-RPC 2.0 protocol transmitted over stdio that standardizes communication between editors (or any client) and AI agents. Think of it as a universal language that lets code editors like Zed, VS Code, and other tools talk to any AI agent in a consistent way -- regardless of which LLM powers it.

The protocol defines how to:

- Create and manage sessions
- Send prompts and receive responses
- Stream output in real time
- Handle tool calls and context

### What does the framework do?

The framework sits between ACP clients and LLM backends. You define your agent logic in Python, pick a backend (Claude, Gemini, Codex, OpenAI, Ollama), and the framework handles all ACP compliance, session management, streaming, and orchestration for you.

```
ACP Clients (Zed, VS Code, etc.)
        |
        |  ACP (JSON-RPC 2.0 over stdio)
        v
+---------------------------+
|   ACP Agent Framework     |
|   (Your Python Code)      |
+---------------------------+
        |
        |  ACP (JSON-RPC 2.0 over stdio)
        v
LLM Backends (Claude, Gemini, Codex, OpenAI, Ollama)
```

The framework also supports HTTP transport, so you can serve your agent as a REST API with Server-Sent Events (SSE) for streaming -- useful for web applications, custom UIs, or any HTTP client.

### Key features

- **Backend-agnostic**: Swap between Claude, Gemini, Codex, OpenAI, or Ollama by changing a single string.
- **No API keys required**: The framework uses your existing CLI-based AI subscriptions (e.g., `claude-agent-acp`, `gemini --acp`).
- **Multiple agent types**: Simple agents, sequential pipelines, routers, and tool agents.
- **Custom tools**: Wrap any Python function as a tool that the LLM can invoke via MCP (Model Context Protocol).
- **Skills system**: Load reusable agent skills from standardized directories.
- **Dual transport**: Serve over ACP stdio (for editors) or HTTP (for web apps).
- **Session management**: Built-in session state, conversation history, and persistence.
- **Guardrails**: Validate inputs and outputs before and after LLM calls.
- **Observability**: Structured logging with configurable verbosity.

---

## Prerequisites

Before you begin, make sure you have the following:

### Required

- **Python 3.10 or later**. Check your version:

  ```bash
  python3 --version
  ```

  If you see `Python 3.10.x` or higher, you are good. If not, install Python 3.10+ from [python.org](https://www.python.org/downloads/) or use your system package manager.

- **pip** (comes with Python). Verify it exists:

  ```bash
  pip --version
  ```

### At least one ACP backend

The framework delegates actual LLM inference to an ACP-compatible backend. You need at least one installed and available on your `PATH`. Here are the supported backends:

| Backend | Command Used | How to Install |
|---------|-------------|----------------|
| Claude | `claude-agent-acp` | `npm i -g @zed-industries/claude-agent-acp` |
| Gemini | `gemini --acp` | `npm i -g @google/gemini-cli` |
| Codex | `npx @zed-industries/codex-acp` | Requires `npx` (comes with Node.js) |
| OpenAI | `openai-acp` | `pip install openai-acp` (community package) |
| Ollama | `ollama-acp` | `pip install ollama-acp` (community package) |

For this guide, we will use Claude as the backend. Install it with:

```bash
npm install -g @zed-industries/claude-agent-acp
```

Verify the installation:

```bash
claude-agent-acp --help
```

If you prefer Gemini:

```bash
npm install -g @google/gemini-cli
gemini --help
```

### Optional

- **Node.js 18+** (needed for Claude, Gemini, and Codex backends)
- **Git** (for cloning the repository)

---

## Installation

### Option 1: Clone and install in development mode (recommended for getting started)

```bash
git clone https://github.com/sanjay3290/agentic-framework-acp.git
cd agentic-framework-acp
pip install -e ".[dev]"
```

The `.[dev]` extra installs development dependencies including pytest, ruff, and httpx for testing.

### Option 2: Install with all extras (includes MCP tool support)

```bash
pip install -e ".[all]"
```

The `.[all]` extra includes everything in `.[dev]` plus the `mcp` package, which is required if you want to use `FunctionTool` to expose Python functions as MCP tools for your LLM backend.

### Option 3: Install with specific extras

If you only need MCP tools (no dev dependencies):

```bash
pip install -e ".[mcp]"
```

### Verify the installation

After installing, verify the CLI is available:

```bash
acp-agent --help
```

You should see output like:

```
Usage: acp-agent [OPTIONS] COMMAND [ARGS]...

  ACP Agent Framework CLI.

Options:
  --help  Show this message and exit.

Commands:
  init  Scaffold a new agent project.
  run   Run an agent.
```

You can also verify the library imports correctly:

```python
python3 -c "from acp_agent_framework import Agent, serve; print('OK')"
```

---

## Your First Agent

Let us build a simple coding assistant agent from scratch.

### Step 1: Create a project directory

```bash
mkdir my-first-agent
cd my-first-agent
```

### Step 2: Create the agent file

Create a file called `agent.py` with the following content:

```python
"""My first ACP agent."""
from acp_agent_framework import Agent, serve

agent = Agent(
    name="my-assistant",
    backend="claude",
    instruction="You are a helpful coding assistant. You write clean, well-documented code.",
)

if __name__ == "__main__":
    serve(agent)
```

Let us break down what each part does:

- **`Agent`**: The primary agent class. It wraps an LLM backend and manages prompt construction, tool bridging, and response handling.
- **`name`**: A unique identifier for your agent. This appears in events and logs.
- **`backend`**: Which LLM backend to use. The string `"claude"` maps to the command `claude-agent-acp` in the backend registry.
- **`instruction`**: The system instruction (system prompt) sent to the LLM. This defines your agent's personality and capabilities. It can be a static string or a callable that receives the current `Context` and returns a string.
- **`serve`**: The entry point that starts serving your agent. By default, it uses ACP stdio transport.

### Step 3: Run the agent over ACP stdio

```bash
python agent.py
```

This starts the agent in ACP stdio mode. It reads JSON-RPC messages from stdin and writes responses to stdout. This is the mode used by editors like Zed and VS Code.

Press `Ctrl+C` to stop the agent.

### Step 4: Run the agent over HTTP

To serve your agent as an HTTP API instead:

```python
"""My first ACP agent - HTTP mode."""
from acp_agent_framework import Agent, serve

agent = Agent(
    name="my-assistant",
    backend="claude",
    instruction="You are a helpful coding assistant. You write clean, well-documented code.",
)

if __name__ == "__main__":
    serve(agent, transport="http", port=8000)
```

Or, more concisely, you can select the transport at runtime. Here is a version that supports both:

```python
"""My first ACP agent - dual transport."""
import sys
from acp_agent_framework import Agent, serve

agent = Agent(
    name="my-assistant",
    backend="claude",
    instruction="You are a helpful coding assistant. You write clean, well-documented code.",
)

if __name__ == "__main__":
    if "--http" in sys.argv:
        serve(agent, transport="http", port=8000)
    else:
        serve(agent)  # ACP stdio (default)
```

Run in HTTP mode:

```bash
python agent.py --http
```

The HTTP server starts on `http://0.0.0.0:8000` and provides the following REST endpoints:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/sessions` | Create a new session. Body: `{"cwd": "/path/to/project"}` |
| `GET` | `/api/sessions/{id}` | Get session info |
| `DELETE` | `/api/sessions/{id}` | Delete a session |
| `POST` | `/api/sessions/{id}/prompt` | Send a prompt. Body: `{"text": "..."}`. Returns SSE stream. |

### Step 5: Test the HTTP agent with curl

In a separate terminal, create a session and send a prompt:

```bash
# Create a session
curl -s -X POST http://localhost:8000/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"cwd": "/tmp"}' | python3 -m json.tool
```

This returns something like:

```json
{
    "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "cwd": "/tmp"
}
```

Now send a prompt using the session ID:

```bash
# Send a prompt (replace SESSION_ID with the actual ID from above)
curl -N -X POST http://localhost:8000/api/sessions/SESSION_ID/prompt \
  -H "Content-Type: application/json" \
  -d '{"text": "Write a Python function to check if a number is prime."}'
```

The response streams back as Server-Sent Events (SSE):

```
data: {"id": "...", "author": "my-assistant", "type": "message", "content": "..."}

data: [DONE]
```

### Step 6: Use a different backend

To switch from Claude to Gemini, change a single line:

```python
agent = Agent(
    name="my-assistant",
    backend="gemini",  # Changed from "claude" to "gemini"
    instruction="You are a helpful coding assistant.",
)
```

No other changes are needed. The framework handles the differences in how each backend is launched and communicated with.

---

## Using the CLI

The framework ships with a CLI tool called `acp-agent` that provides two commands: `init` and `run`.

### Scaffolding a new agent project

The `init` command creates a new directory with a starter `agent.py` file:

```bash
acp-agent init my-agent
```

This creates:

```
my-agent/
  agent.py
```

The generated `agent.py` looks like this:

```python
"""Example agent created with acp-agent init."""
from acp_agent_framework.agents import Agent

agent = Agent(
    name="my-agent",
    backend="claude",
    instruction="You are a helpful assistant.",
)

if __name__ == "__main__":
    from acp_agent_framework.server.serve import serve
    serve(agent)
```

### Running an agent

The `run` command imports an agent object from a Python module and starts serving it. The format is `module:attribute`:

```bash
# Run the scaffolded agent (ACP stdio)
acp-agent run my_agent.agent:agent
```

Here, `my_agent.agent` is the Python module path (the file `my_agent/agent.py`), and `agent` is the variable name of the agent object inside that module. If you omit the attribute name, it defaults to `agent`:

```bash
# Equivalent to the above
acp-agent run my_agent.agent
```

### Running as an HTTP server

Use the `-t` (transport) and `-p` (port) options:

```bash
acp-agent run my_agent.agent:agent -t http -p 8000
```

### All CLI options for `run`

```bash
acp-agent run --help
```

```
Usage: acp-agent run [OPTIONS] MODULE_PATH

  Run an agent. MODULE_PATH is 'module:attribute' (e.g. 'my_agent:agent').

Options:
  -t, --transport [acp|http]  Transport protocol (default: acp)
  --host TEXT                 HTTP host to bind to (default: 0.0.0.0)
  -p, --port INTEGER          HTTP port to bind to (default: 8000)
  --help                      Show this message and exit.
```

### Important: Python module path resolution

The `MODULE_PATH` must be importable by Python. This means:

- The module's directory must be on the Python path
- If your agent is in `my_agent/agent.py`, you run the command from the parent directory of `my_agent/`
- Use dots for nested modules: `my_agent.subpackage.agent:agent`

If you get an import error, try adding the current directory to `PYTHONPATH`:

```bash
PYTHONPATH=. acp-agent run my_agent.agent:agent
```

---

## Understanding Context

The `Context` object is the central data container that flows through every agent invocation. It carries session identity, working directory, shared state, input/output values, per-agent outputs, and conversation history. Understanding it is essential for building multi-agent pipelines and stateful agents.

### Context attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `session_id` | `str` | Unique identifier for the current session. Created by the ACP server or HTTP server when a client connects. |
| `cwd` | `str` | The working directory of the client. For editor integrations, this is the project root. Agents use this to understand which project they are operating on. |
| `state` | `State` | A key-value store shared across all agents in a pipeline. Supports delta tracking so you can see what changed during each agent run. |
| `_input` | `Any` | The current input to the agent (usually the user's prompt text). Access via `get_input()` and `set_input()`. |
| `_output` | `Any` | The output produced by the most recent agent. Access via `get_output()` and `set_output()`. |
| `_agent_outputs` | `dict[str, Any]` | A map of agent name to output. When agents in a pipeline set `output_key`, their results are stored here. Access via `get_agent_output(name)` and `set_agent_output(name, value)`. |
| `_history` | `list[dict[str, str]]` | Conversation history for multi-turn agents. Each entry is `{"role": "user" or "assistant", "content": "..."}`. Access via `get_history()`, `add_message()`, and `clear_history()`. |

### Creating a Context manually

When writing tests or running agents programmatically (outside of ACP/HTTP), you create a Context yourself:

```python
from acp_agent_framework import Context

ctx = Context(session_id="test-session-1", cwd="/path/to/project")
ctx.set_input("Write a function to sort a list.")
```

### Using State for cross-agent communication

The `State` object on a Context is how agents in a `SequentialAgent` pipeline communicate. When an agent has an `output_key`, its output is automatically stored in the state under that key:

```python
from acp_agent_framework import Agent, SequentialAgent, Context

researcher = Agent(
    name="researcher",
    backend="claude",
    instruction="Research the given topic. Provide detailed findings.",
    output_key="research",  # Output is stored in state["research"]
)

summarizer = Agent(
    name="summarizer",
    backend="claude",
    instruction=lambda ctx: f"Summarize the following research:\n\n{ctx.state.get('research', '')}",
    output_key="summary",
)

pipeline = SequentialAgent(
    name="research-pipeline",
    agents=[researcher, summarizer],
)
```

When this pipeline runs:

1. The `researcher` agent runs, produces output, and stores it in `state["research"]`.
2. The `summarizer` agent runs, reads `state["research"]` via its dynamic instruction, and stores its output in `state["summary"]`.

### State delta tracking

The `State` object tracks what changed during each agent run. This is useful for observability and debugging:

```python
from acp_agent_framework import State

state = State()
state.set("research", "Python was created by Guido van Rossum.")
state.set("confidence", 0.95)

# See what changed since the last commit
print(state.get_delta())
# {"research": "Python was created by Guido van Rossum.", "confidence": 0.95}

# Commit clears the delta (the data remains)
state.commit()
print(state.get_delta())
# {}
```

### Temporary state keys

Keys prefixed with `temp:` are excluded from persistence. Use them for transient data that should not survive a session save/restore:

```python
state.set("temp:raw_api_response", large_json_blob)
state.set("processed_result", cleaned_data)

# Only "processed_result" will be saved
persistable = state.get_persistable()
```

### Conversation history (multi-turn)

When an `Agent` has `multi_turn=True`, it automatically records user inputs and assistant responses in the context history. Subsequent prompts in the same session include the full conversation:

```python
agent = Agent(
    name="chat-agent",
    backend="claude",
    instruction="You are a conversational assistant.",
    multi_turn=True,
)
```

You can also manage history manually:

```python
ctx.add_message("user", "What is Python?")
ctx.add_message("assistant", "Python is a programming language.")

# Later, retrieve the full conversation
history = ctx.get_history()
for msg in history:
    print(f"{msg['role']}: {msg['content']}")

# Clear history to start fresh
ctx.clear_history()
```

---

## Adding Tools to Your Agent

Tools let the LLM backend call Python functions during inference. The framework bridges your tools to the backend via MCP (Model Context Protocol), so the LLM can discover and invoke them.

### Creating a FunctionTool

Wrap any Python function with `FunctionTool`:

```python
from acp_agent_framework import Agent, FunctionTool, serve

def lookup_user(username: str) -> str:
    """Look up a user by their username and return their profile."""
    # In a real app, this would query a database
    return f"User {username}: Senior Engineer, joined 2020"

def search_docs(query: str) -> str:
    """Search the documentation for a given query string."""
    return f"Documentation results for: {query}"

agent = Agent(
    name="tool-agent",
    backend="claude",
    instruction="You are a helpful assistant. Use the available tools to answer questions.",
    tools=[
        FunctionTool(lookup_user),
        FunctionTool(search_docs),
    ],
)

if __name__ == "__main__":
    serve(agent)
```

The `FunctionTool` automatically extracts the function name, docstring (used as the tool description), and parameter types from the function signature. The LLM sees these tools and can choose to call them during inference.

### Requirements for tool functions

- Must have **type annotations** on all parameters (so the MCP schema can be generated).
- Must have a **docstring** (used as the tool description shown to the LLM).
- Must return a **string** (the result sent back to the LLM).

### Using ToolAgent for direct tool execution (no LLM)

If you want to execute tools directly without an LLM backend, use `ToolAgent`:

```python
from acp_agent_framework import ToolAgent, FunctionTool, Context

def check_health(url: str) -> str:
    """Check the health of a service at the given URL."""
    import urllib.request
    try:
        response = urllib.request.urlopen(url, timeout=5)
        return f"Status: {response.status}"
    except Exception as e:
        return f"Error: {e}"

async def execute(ctx, tools):
    url = ctx.get_input()
    return tools["check_health"].run(url=url)

agent = ToolAgent(
    name="health-checker",
    tools=[FunctionTool(check_health)],
    execute=execute,
    output_key="status",
)
```

`ToolAgent` gives you full control over which tools run and in what order, without involving an LLM.

---

## Multi-Turn Conversations

By default, each prompt to an agent is independent -- it has no memory of previous exchanges. To enable conversational memory within a session, set `multi_turn=True`:

```python
agent = Agent(
    name="chat-agent",
    backend="claude",
    instruction="You are a conversational assistant. Remember what the user said earlier.",
    multi_turn=True,
)
```

When `multi_turn` is enabled:

1. After each agent run, the user input and assistant response are appended to `ctx._history`.
2. On subsequent runs in the same session, the full conversation history is included in the prompt sent to the backend.
3. The LLM sees the entire conversation and can reference earlier messages.

This only works within a single session. If the session is destroyed (e.g., the editor disconnects), the history is lost unless you use session persistence.

---

## Streaming Responses

For long-running responses, you can enable streaming so the client receives chunks as they are generated:

```python
agent = Agent(
    name="streaming-agent",
    backend="claude",
    instruction="You are a helpful assistant.",
    stream=True,
)
```

When streaming is enabled:

- The framework emits `Event` objects with `type="stream_chunk"` for each chunk received from the backend.
- After all chunks are collected, a final `Event` with `type="message"` is emitted containing the complete response.
- Over HTTP, these events are delivered as Server-Sent Events (SSE).
- Over ACP stdio, the events are delivered as JSON-RPC notifications.

---

## Session Persistence

The framework includes a `JsonSessionStore` for saving and restoring session state to disk:

```python
from pathlib import Path
from acp_agent_framework import Context, State
from acp_agent_framework.persistence import JsonSessionStore

# Create a store
store = JsonSessionStore(Path("/tmp/agent-sessions"))

# Save session state
ctx = Context(session_id="session-123", cwd="/projects/my-app")
ctx.state.set("last_topic", "Python async patterns")
store.save(ctx.session_id, {
    "cwd": ctx.cwd,
    "state": ctx.state.get_persistable(),
})

# Later, restore the session
data = store.load("session-123")
if data:
    restored_ctx = Context(
        session_id="session-123",
        cwd=data["cwd"],
        state=State(data.get("state")),
    )
    print(restored_ctx.state.get("last_topic"))
    # "Python async patterns"
```

The store supports:

- **`save(session_id, data)`** -- Write session data to a JSON file.
- **`load(session_id)`** -- Read session data. Returns `None` if the session does not exist.
- **`delete(session_id)`** -- Remove a session file.
- **`list_sessions()`** -- List all saved session IDs.

State keys prefixed with `temp:` are excluded from `get_persistable()`, so temporary data is never written to disk.

---

## Next Steps

Now that you have a working agent, explore these areas to build more sophisticated systems:

### Agent types

- **SequentialAgent** -- Chain multiple agents into a pipeline where each agent's output feeds into the next. See the [sequential pipeline example](../examples/sequential_pipeline/agent.py).
- **RouterAgent** -- Route incoming requests to different specialist agents based on keyword matching. See the [router agent example](../examples/router_agent/agent.py).
- **ToolAgent** -- Execute tools directly without an LLM backend, giving you full programmatic control.

### Tools and MCP

- **FunctionTool** -- Wrap Python functions as MCP tools the LLM can call.
- **McpBridge** -- The internal component that starts an MCP stdio server and connects your tools to the backend.
- **AgentTool** -- Wrap an entire agent as a tool that another agent can invoke.

### Skills

- Load reusable agent skills from `.agents/skills/` directories following the [agentskills.io](https://agentskills.io) specification.
- Skills are folders containing a `SKILL.md` file with YAML frontmatter and markdown instructions.
- Supports dependency resolution between skills.
- See the [chat agent example](../examples/chat_agent/agent.py) for a skills-based agent.

### Guardrails

- Validate and transform inputs before they reach the LLM.
- Validate and transform outputs before they reach the user.
- Raise `GuardrailError` to block requests that fail validation.

### Custom backends

- Register your own ACP-compatible backend using `BackendRegistry`:

  ```python
  from acp_agent_framework import BackendConfig, BackendRegistry

  registry = BackendRegistry()
  registry.register("my-backend", BackendConfig(
      command="my-agent-binary",
      args=["--acp"],
      timeout=60.0,
      max_retries=5,
  ))

  agent = Agent(name="custom", backend="my-backend", instruction="...")
  ```

### Observability

- Use `AgentLogger` and `get_logger()` for structured logging throughout your agent pipelines.

### Running the test suite

```bash
# Run all unit tests (excludes integration tests by default)
pytest tests/ -v

# Run integration tests (requires real backends installed)
pytest tests/ -v -m integration

# Lint the codebase
ruff check src/ tests/
```

### Project structure reference

```
src/acp_agent_framework/
  agents/
    base.py            BaseAgent (abstract base class)
    agent.py            Agent (LLM-backed with tools and skills)
    tool_agent.py       ToolAgent (direct tool execution, no LLM)
    sequential.py       SequentialAgent (pipeline chaining)
    router.py           RouterAgent (keyword-based routing)
  backends/
    registry.py         BackendConfig and BackendRegistry (singleton)
    acp_backend.py      AcpBackend (subprocess management for backends)
  server/
    acp_server.py       ACP protocol implementation (JSON-RPC over stdio)
    http_server.py      FastAPI REST API with SSE streaming
    serve.py            serve() entry point
  tools/
    base.py             BaseTool (abstract)
    function_tool.py    FunctionTool (wraps Python callables)
    agent_tool.py       AgentTool (wraps agents as tools)
    mcp_bridge.py       McpBridge (tools to MCP server bridge)
    mcp_tool_server.py  Standalone MCP stdio server
  skills/
    skill.py            Skill dataclass
    loader.py           SkillLoader (discover and load skills)
  context.py            Context (session state container)
  state.py              State (key-value store with delta tracking)
  events.py             Event and EventActions
  persistence.py        JsonSessionStore (JSON file session storage)
  guardrails.py         Guardrail and GuardrailError
  observability.py      AgentLogger and get_logger
  cli.py                CLI tool (acp-agent)
```
