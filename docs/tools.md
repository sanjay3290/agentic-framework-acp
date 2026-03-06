# Tools System

## Overview

Tools let agents invoke Python functions during LLM inference. In the ACP Agent Framework, tools are bridged to backends via MCP (Model Context Protocol). The framework exposes `FunctionTool` instances as MCP tools that the LLM backend can call.

The flow works as follows:

1. You define Python functions and wrap them in `FunctionTool` (or use `AgentTool` to wrap another agent).
2. You pass the tools to an `Agent` via the `tools` parameter.
3. When the agent runs, an `McpBridge` serializes the tool definitions to a temporary JSON file and spawns an MCP stdio server (`mcp_tool_server.py`).
4. The ACP backend connects to this MCP server, making the tools available to the LLM.
5. When the LLM decides to call a tool, the MCP server imports and invokes the original Python function, returning the result to the LLM.

All tool classes are importable from the top-level package:

```python
from acp_agent_framework import BaseTool, FunctionTool, AgentTool, McpBridge
```

---

## BaseTool

`BaseTool` is the abstract base class for all tools. It defines the interface that every tool must implement.

**Location:** `src/acp_agent_framework/tools/base.py`

### Attributes

| Attribute     | Type  | Description                                  |
|---------------|-------|----------------------------------------------|
| `name`        | `str` | The name of the tool, used to identify it.   |
| `description` | `str` | A human-readable description of what the tool does. |

### Methods

#### `run(args: dict[str, Any]) -> Any`

Execute the tool synchronously. This is an abstract method that subclasses must implement.

**Parameters:**
- `args` -- A dictionary of keyword arguments to pass to the tool's underlying implementation.

**Returns:** The result of the tool execution. The return type depends on the implementation.

#### `async arun(args: dict[str, Any]) -> Any`

Execute the tool asynchronously. The default implementation runs the synchronous `run()` method in a thread pool executor via `asyncio.get_event_loop().run_in_executor()`. Subclasses can override this to provide native async behavior.

**Parameters:**
- `args` -- A dictionary of keyword arguments to pass to the tool's underlying implementation.

**Returns:** The result of the tool execution.

#### `get_schema() -> dict[str, Any]`

Return the tool's schema as a dictionary. This is an abstract method that subclasses must implement. The schema includes the tool name, description, and parameter definitions.

**Returns:** A dictionary describing the tool's interface.

### Implementing a Custom Tool

To create a custom tool, subclass `BaseTool` and implement `run()` and `get_schema()`:

```python
from typing import Any
from acp_agent_framework import BaseTool


class DatabaseLookup(BaseTool):
    def __init__(self, connection_string: str) -> None:
        self.name = "database_lookup"
        self.description = "Look up a record in the database by ID."
        self._conn_str = connection_string

    def run(self, args: dict[str, Any]) -> Any:
        record_id = args["record_id"]
        # ... perform database query ...
        return {"id": record_id, "status": "found"}

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "record_id": {"type": "str", "description": "The record ID to look up"},
            },
        }
```

---

## FunctionTool

`FunctionTool` wraps any Python callable (function or lambda) as a tool. It automatically extracts the tool name, description, and parameter schema from the function itself.

**Location:** `src/acp_agent_framework/tools/function_tool.py`

### Constructor

```python
FunctionTool(func: Callable)
```

**Parameters:**
- `func` -- Any Python callable. The function's `__name__` becomes the tool name, its docstring becomes the description, and its type-annotated parameters become the parameter schema.

### Auto-Extraction Behavior

| Source                    | Extracted As         |
|---------------------------|----------------------|
| `func.__name__`          | `tool.name`          |
| `func.__doc__` (stripped) | `tool.description`   |
| Type hints on parameters  | Parameter schema types |
| Default values on parameters | Parameter schema defaults |

### Synchronous Function Example

```python
from acp_agent_framework import FunctionTool


def search_docs(query: str) -> str:
    """Search documentation for relevant results."""
    return f"Results for: {query}"


tool = FunctionTool(search_docs)

# Auto-extracted attributes:
assert tool.name == "search_docs"
assert tool.description == "Search documentation for relevant results."

# Synchronous execution:
result = tool.run({"query": "hello"})
assert result == "Results for: hello"

# Schema:
schema = tool.get_schema()
# {
#     "name": "search_docs",
#     "description": "Search documentation for relevant results.",
#     "parameters": {
#         "query": {"type": "str"}
#     }
# }
```

### Async Function Example

When wrapping an async function, use `arun()` for execution. Calling `run()` on an async function raises `TypeError`.

```python
import asyncio
from acp_agent_framework import FunctionTool


async def fetch_url(url: str, timeout: int = 30) -> str:
    """Fetch content from a URL."""
    # ... async HTTP request ...
    return f"Content from {url}"


tool = FunctionTool(fetch_url)

# Auto-extracted attributes:
assert tool.name == "fetch_url"
assert tool.description == "Fetch content from a URL."

# Async execution:
result = asyncio.run(tool.arun({"url": "https://example.com"}))
assert result == "Content from https://example.com"

# Sync execution raises TypeError:
try:
    tool.run({"url": "https://example.com"})
except TypeError as e:
    print(e)
    # "Cannot call sync run() on async function 'fetch_url'. Use arun() instead."

# Schema includes default values:
schema = tool.get_schema()
# {
#     "name": "fetch_url",
#     "description": "Fetch content from a URL.",
#     "parameters": {
#         "url": {"type": "str"},
#         "timeout": {"type": "int", "default": 30}
#     }
# }
```

### How run() and arun() Differ for FunctionTool

| Method   | Sync function              | Async function                              |
|----------|----------------------------|---------------------------------------------|
| `run()`  | Calls `func(**args)` directly | Raises `TypeError`                         |
| `arun()` | Calls `func(**args)` directly (no executor) | Calls `await func(**args)`  |

Note that `FunctionTool.arun()` overrides the base class default. For sync functions it calls them directly (not in an executor). For async functions it awaits them natively.

---

## AgentTool

`AgentTool` wraps a `BaseAgent` as a tool, enabling agent-to-agent communication. One agent can delegate work to another agent by invoking it as a tool call.

**Location:** `src/acp_agent_framework/tools/agent_tool.py`

### Constructor

```python
AgentTool(agent: BaseAgent, cwd: str = ".")
```

**Parameters:**
- `agent` -- A `BaseAgent` instance to wrap. Must be an instance of `BaseAgent` or a subclass; otherwise `TypeError` is raised.
- `cwd` -- Working directory for the context created when running the agent. Defaults to `"."`.

### Auto-Extraction Behavior

| Source                          | Extracted As        |
|----------------------------------|---------------------|
| `agent.name`                    | `tool.name`         |
| `agent.description` (or fallback) | `tool.description` |

If the agent has no `description`, the tool description defaults to `"Delegate to {agent.name} agent"`.

### Input Arguments

The tool accepts a dictionary with either a `prompt` or `input` key:

| Key      | Description                        |
|----------|------------------------------------|
| `prompt` | Primary key. The input text for the wrapped agent. |
| `input`  | Fallback key. Used if `prompt` is not present.     |

### Execution Flow

When `AgentTool` is invoked:

1. Extracts the prompt from `args["prompt"]` or `args["input"]`.
2. Creates a new `Context` with `session_id="agent-tool-{name}"` and the configured `cwd`.
3. Sets the prompt as the context input via `ctx.set_input()`.
4. Runs the wrapped agent via `agent.run(ctx)` and iterates over emitted events.
5. Collects all events of type `"message"` and joins their content with newlines.
6. Returns the joined message content, or falls back to `ctx.get_output()` if no message events were emitted.

### Schema

The schema exposes a single `prompt` parameter:

```python
{
    "name": "<agent_name>",
    "description": "<agent_description>",
    "parameters": {
        "prompt": {"type": "str", "description": "Input prompt for the agent"},
    },
}
```

### Basic Example

```python
import asyncio
from acp_agent_framework import AgentTool

# Assume EchoAgent is a BaseAgent subclass that echoes its input
from my_agents import EchoAgent

researcher = EchoAgent(name="researcher", description="Research any topic")
tool = AgentTool(researcher, cwd="/tmp")

# Async execution:
result = asyncio.run(tool.arun({"prompt": "research quantum computing"}))
print(result)  # Output depends on EchoAgent implementation

# Sync execution (blocks the event loop):
result = tool.run({"prompt": "research quantum computing"})
print(result)
```

### Agent Orchestration with ToolAgent

A powerful pattern is combining `AgentTool` with `ToolAgent` to create an orchestrator that delegates to specialized agents without requiring an LLM backend:

```python
import asyncio
from acp_agent_framework import Agent, AgentTool, ToolAgent, Context


# Define specialized agents
summarizer = Agent(
    name="summarizer",
    backend="claude",
    instruction="Summarize the given text concisely.",
)

translator = Agent(
    name="translator",
    backend="claude",
    instruction="Translate the given text to Spanish.",
)

# Wrap them as tools
summarizer_tool = AgentTool(summarizer, cwd="/tmp")
translator_tool = AgentTool(translator, cwd="/tmp")


# Define the orchestration logic
async def orchestrate(ctx: Context, tools: dict) -> str:
    user_input = ctx.get_input()

    # First summarize
    summary = await tools["summarizer"].arun({"prompt": user_input})

    # Then translate the summary
    translated = await tools["translator"].arun({"prompt": summary})

    return f"Summary: {summary}\nTranslation: {translated}"


# Create the orchestrator
orchestrator = ToolAgent(
    name="orchestrator",
    description="Summarize and translate text",
    tools=[summarizer_tool, translator_tool],
    execute=orchestrate,
)

# Run it
async def main():
    ctx = Context(session_id="demo", cwd="/tmp")
    ctx.set_input("A long article about machine learning...")
    async for event in orchestrator.run(ctx):
        print(f"[{event.type}] {event.content}")

asyncio.run(main())
```

---

## McpBridge

`McpBridge` is the internal mechanism that bridges framework tools to ACP backends via MCP (Model Context Protocol). Users do not interact with `McpBridge` directly -- the `Agent` class manages it automatically when tools are provided.

**Location:** `src/acp_agent_framework/tools/mcp_bridge.py`

### How It Works

1. **Serialization** -- `McpBridge` takes a list of `BaseTool` instances and serializes their definitions (name, description, parameters) to a temporary JSON file. For `FunctionTool` instances, it also records the function's module path and qualified name so the MCP server can import and call the real function.

2. **MCP Server** -- The bridge returns an `acp.schema.McpServerStdio` configuration that points to `mcp_tool_server.py`. This script is spawned as a subprocess by the ACP backend.

3. **Tool Registration** -- The `mcp_tool_server.py` script reads the JSON file, imports each function by its module path and qualified name, and registers it with FastMCP. If a tool has no importable callable, a stub function is registered instead.

4. **Lifecycle** -- The bridge is started before the backend session and stopped (cleaning up temp files) after the backend session ends.

### Internal API

```python
bridge = McpBridge(tools=[tool1, tool2])
bridge.start()                   # Writes tool definitions to a temp JSON file
config = bridge.get_mcp_config() # Returns McpServerStdio config for the backend
bridge.stop()                    # Removes the temp JSON file
```

### What Happens Inside Agent.run()

When you pass tools to an `Agent`, the following happens automatically in `Agent.run()`:

```python
# Simplified view of Agent.run() internals:
mcp_bridge = McpBridge(self.tools)
mcp_bridge.start()
mcp_servers = [mcp_bridge.get_mcp_config()]

backend = self._get_backend()
await backend.start()
session_id = await backend.new_session(ctx.cwd, mcp_servers=mcp_servers)

# ... prompt the LLM, which can now call the tools ...

await backend.stop()
mcp_bridge.stop()
```

### MCP Tool Server

The `mcp_tool_server.py` script (`src/acp_agent_framework/tools/mcp_tool_server.py`) is the subprocess that the ACP backend spawns. It:

1. Reads tool definitions from the JSON file passed as a command-line argument.
2. For each tool with a `module` and `qualname`, imports the original Python function.
3. For tools without an importable callable, creates a stub that returns a placeholder message.
4. Registers all tools with `FastMCP` and runs the server on stdio transport.

This script is not intended to be invoked directly by users.

---

## Using Tools with Agent

The most common pattern is passing `FunctionTool` instances to an `Agent`. The agent's LLM backend decides when and how to call the tools during inference.

```python
import asyncio
from acp_agent_framework import Agent, FunctionTool, Context


def search_docs(query: str) -> str:
    """Search the documentation for relevant articles."""
    # In practice, this would query a search index
    return f"Found 3 articles matching '{query}'"


def calculate(expression: str) -> str:
    """Evaluate a mathematical expression."""
    try:
        result = eval(expression)
        return str(result)
    except Exception as e:
        return f"Error: {e}"


agent = Agent(
    name="assistant",
    backend="claude",
    instruction="You are a helpful assistant. Use the available tools to answer questions.",
    tools=[FunctionTool(search_docs), FunctionTool(calculate)],
)


async def main():
    ctx = Context(session_id="demo", cwd=".")
    ctx.set_input("What is 42 * 17? Also search for articles about Python asyncio.")
    async for event in agent.run(ctx):
        if event.type == "message":
            print(event.content)

asyncio.run(main())
```

In this example, the LLM receives the tool schemas via MCP and can decide to call `search_docs` and `calculate` as part of generating its response. The results are returned to the LLM, which incorporates them into the final output.

---

## Using Tools with ToolAgent

`ToolAgent` executes tools directly through a user-defined `execute` function, without an LLM backend. This is useful for deterministic pipelines, testing, and orchestration logic where you want full control over which tools are called and in what order.

**Location:** `src/acp_agent_framework/agents/tool_agent.py`

### Constructor

```python
ToolAgent(
    name: str,
    tools: list[BaseTool],
    execute: Callable,
    description: str = "",
    output_key: str | None = None,
)
```

**Parameters:**
- `name` -- The agent name.
- `tools` -- A list of `BaseTool` instances. These are passed to the `execute` function as a dict keyed by tool name.
- `execute` -- An async callable with signature `async (ctx: Context, tools: dict[str, BaseTool]) -> str`. This function contains the orchestration logic.
- `description` -- Optional description of the agent.
- `output_key` -- Optional state key to store the result in `ctx.state`.

### Execution Flow

1. If `before_run` is set, it is called first.
2. A `tools_dict` is built: `{tool.name: tool for tool in self.tools}`.
3. The `execute` function is called with `(ctx, tools_dict)`.
4. The result is stored via `ctx.set_output()` and optionally in `ctx.state`.
5. A single `Event` of type `"tool_result"` is yielded with the result.
6. If `after_run` is set, it is called last.

### Complete Example

```python
import asyncio
from acp_agent_framework import FunctionTool, ToolAgent, Context


def search_docs(query: str) -> str:
    """Search documentation for relevant results."""
    return f"Found: article about '{query}'"


def format_output(text: str, style: str = "plain") -> str:
    """Format text in the given style."""
    if style == "uppercase":
        return text.upper()
    return text


search_tool = FunctionTool(search_docs)
format_tool = FunctionTool(format_output)


async def pipeline(ctx: Context, tools: dict) -> str:
    query = ctx.get_input()

    # Step 1: Search
    raw_result = tools["search_docs"].run({"query": query})

    # Step 2: Format
    formatted = tools["format_output"].run({"text": raw_result, "style": "uppercase"})

    return formatted


agent = ToolAgent(
    name="search-pipeline",
    description="Search and format documentation results",
    tools=[search_tool, format_tool],
    execute=pipeline,
    output_key="pipeline_result",
)


async def main():
    ctx = Context(session_id="demo", cwd=".")
    ctx.set_input("asyncio patterns")
    async for event in agent.run(ctx):
        print(f"[{event.type}] {event.content}")
        # [tool_result] FOUND: ARTICLE ABOUT 'ASYNCIO PATTERNS'

    # Result is also in state:
    print(ctx.state.get("pipeline_result"))
    # FOUND: ARTICLE ABOUT 'ASYNCIO PATTERNS'

asyncio.run(main())
```

### Using Async Tools in ToolAgent

When your tools wrap async functions, use `arun()` inside the execute function:

```python
async def async_pipeline(ctx: Context, tools: dict) -> str:
    query = ctx.get_input()
    result = await tools["fetch_url"].arun({"url": f"https://api.example.com/search?q={query}"})
    return result


agent = ToolAgent(
    name="async-searcher",
    tools=[FunctionTool(fetch_url)],
    execute=async_pipeline,
)
```

---

## Summary

| Class          | Purpose                                         | Requires LLM | User-facing |
|----------------|--------------------------------------------------|--------------|-------------|
| `BaseTool`     | Abstract base class for all tools                | No           | Yes (subclass) |
| `FunctionTool` | Wraps a Python callable as a tool                | No           | Yes         |
| `AgentTool`    | Wraps a BaseAgent as a tool for delegation       | No           | Yes         |
| `McpBridge`    | Bridges tools to ACP backends via MCP            | N/A          | No (internal) |
| `ToolAgent`    | Runs tools via user-defined logic, no LLM needed | No           | Yes         |
| `Agent`        | LLM-backed agent that can use tools via MCP      | Yes          | Yes         |
