# Backends and Serving

This document provides a comprehensive reference for the backend system and serving infrastructure in the ACP Agent Framework. It covers how the framework communicates with external AI processes, how to configure and register custom backends, the internal subprocess lifecycle, retry mechanics, and the multiple transport options for exposing agents to clients.

---

## Table of Contents

1. [Backends Overview](#backends-overview)
2. [Built-in Backends](#built-in-backends)
3. [BackendConfig](#backendconfig)
4. [BackendRegistry](#backendregistry)
5. [AcpBackend Internals](#acpbackend-internals)
6. [Retry Logic](#retry-logic)
7. [Serving Agents](#serving-agents)
   - [ACP (stdio)](#acp-stdio)
   - [HTTP](#http)
   - [Web UI Dashboard](#web-ui-dashboard)
8. [CLI](#cli)
9. [Complete Examples](#complete-examples)

---

## Backends Overview

In the ACP Agent Framework, a **backend** is an external process that implements the [ACP (Agent Communication Protocol)](https://github.com/AcpProtocol/acp). The framework does not contain any LLM inference logic itself. Instead, it spawns backends as subprocesses and communicates with them over **JSON-RPC 2.0 on stdio** (stdin/stdout pipes).

This architecture provides several key properties:

- **Subscription reuse** -- You use your existing AI subscriptions (Claude Pro, Gemini, etc.) through their official CLI tools. No API keys or per-token billing required.
- **Backend agnosticism** -- Agents are defined independently of which LLM powers them. Switching from Claude to Gemini is a one-line change (`backend="gemini"`).
- **Process isolation** -- Each agent run spawns a fresh backend process. If the backend crashes, the framework catches it cleanly without corrupting shared state.
- **Protocol standardization** -- All backends speak the same ACP protocol, so the framework treats them uniformly regardless of the underlying model.

The communication flow for a single agent prompt looks like this:

```
Framework                          Backend Process
   |                                     |
   |-- spawn subprocess (command+args) ->|
   |                                     |
   |-- initialize (JSON-RPC) ----------->|
   |<------------ InitializeResponse ----|
   |                                     |
   |-- new_session (JSON-RPC) ---------->|
   |<------------ NewSessionResponse ----|
   |                                     |
   |-- prompt (JSON-RPC) --------------->|
   |<------------ session_update --------|  (one or more)
   |<------------ PromptResponse --------|
   |                                     |
   |-- close / terminate --------------->|
```

---

## Built-in Backends

The framework ships with five pre-registered backends. These are defined in `DEFAULT_BACKENDS` within the `BackendRegistry` and are available immediately without any registration code.

| Backend  | Registry Name | Command              | Arguments     | Install Command                                     | Notes                                          |
|----------|---------------|----------------------|---------------|------------------------------------------------------|-------------------------------------------------|
| Claude   | `claude`      | `claude-agent-acp`   | (none)        | `npm i -g @zed-industries/claude-agent-acp`          | Uses your Claude subscription via the Zed ACP bridge |
| Gemini   | `gemini`      | `gemini`             | `["--acp"]`   | `npm i -g @google/gemini-cli`                        | Google Gemini CLI with ACP mode flag            |
| Codex    | `codex`       | `npx`                | `["@zed-industries/codex-acp"]` | Requires `npx` (bundled with Node.js)  | Runs via npx; downloads on first use            |
| OpenAI   | `openai`      | `openai-acp`         | (none)        | `pip install openai-acp` (hypothetical)              | Planned; not yet publicly available             |
| Ollama   | `ollama`      | `ollama-acp`         | (none)        | `pip install ollama-acp` (hypothetical)              | Planned; for local model inference via Ollama   |

To use a built-in backend, reference it by name when creating an agent:

```python
from acp_agent_framework import Agent

agent = Agent(
    name="my-agent",
    backend="claude",  # or "gemini", "codex", "openai", "ollama"
    instruction="You are a helpful assistant.",
)
```

The framework will look up the corresponding `BackendConfig` in the registry and use its `command` and `args` to spawn the process.

---

## BackendConfig

`BackendConfig` is a Pydantic `BaseModel` that defines everything the framework needs to spawn and manage a backend process. It is defined in `src/acp_agent_framework/backends/registry.py`.

### Fields

| Field              | Type              | Default | Description                                                                                     |
|--------------------|-------------------|---------|-------------------------------------------------------------------------------------------------|
| `command`          | `str`             | (required) | The binary or command to execute. Must be available on `$PATH` or specified as an absolute path. |
| `args`             | `list[str]`       | `[]`    | Command-line arguments passed to the binary after the command name.                              |
| `env`              | `dict[str, str]`  | `{}`    | Extra environment variables merged into the current environment before spawning.                 |
| `timeout`          | `float`           | `120.0` | Maximum time in seconds to wait for a single prompt response before raising `TimeoutError`.      |
| `max_retries`      | `int`             | `3`     | Number of retry attempts for transient failures (timeout, connection, OS errors).                 |
| `retry_base_delay` | `float`           | `1.0`   | Base delay in seconds for exponential backoff between retries.                                   |

### Definition

```python
from pydantic import BaseModel, Field

class BackendConfig(BaseModel):
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    timeout: float = 120.0
    max_retries: int = 3
    retry_base_delay: float = 1.0
```

### Usage Examples

Minimal configuration (command only):

```python
from acp_agent_framework import BackendConfig

config = BackendConfig(command="claude-agent-acp")
```

Full configuration with all fields:

```python
config = BackendConfig(
    command="my-custom-backend",
    args=["--acp", "--model", "large", "--verbose"],
    env={
        "MY_API_KEY": "sk-...",
        "MY_LOG_LEVEL": "debug",
    },
    timeout=300.0,        # 5 minutes for long-running tasks
    max_retries=5,        # More retries for unreliable connections
    retry_base_delay=2.0, # Start with 2s backoff
)
```

The `env` dictionary is merged with the current process environment (`os.environ`) when spawning the subprocess. Existing variables are preserved; keys in `env` override any conflicts.

---

## BackendRegistry

The `BackendRegistry` is a **singleton** that maps string names to `BackendConfig` instances. It is the central lookup table used by `Agent` to resolve which backend process to spawn.

### Singleton Behavior

All instantiations of `BackendRegistry` return the same object. This means registrations made anywhere in your code are visible everywhere:

```python
from acp_agent_framework import BackendRegistry

r1 = BackendRegistry()
r2 = BackendRegistry()
assert r1 is r2  # True -- same instance
```

The singleton is implemented via `__new__`:

```python
class BackendRegistry:
    _instance = None
    _backends: dict[str, BackendConfig] = {}

    def __new__(cls) -> "BackendRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._backends = dict(DEFAULT_BACKENDS)
        return cls._instance
```

On first instantiation, it copies `DEFAULT_BACKENDS` (the five built-in backends) into its internal dictionary. Subsequent instantiations skip initialization and return the existing instance.

### Methods

#### `register(name: str, config: BackendConfig) -> None`

Registers a new backend or overwrites an existing one.

```python
from acp_agent_framework import BackendConfig, BackendRegistry

registry = BackendRegistry()
registry.register("my-backend", BackendConfig(
    command="my-agent-binary",
    args=["--acp"],
    timeout=60.0,
    max_retries=5,
))
```

After registration, any agent can reference the new backend by name:

```python
agent = Agent(name="test", backend="my-backend", instruction="...")
```

You can also overwrite a built-in backend to customize its defaults:

```python
registry.register("claude", BackendConfig(
    command="claude-agent-acp",
    timeout=300.0,      # Override default 120s timeout
    max_retries=10,     # More retries
))
```

#### `get(name: str) -> BackendConfig`

Retrieves a backend configuration by name. Raises `KeyError` with a descriptive message if the name is not found.

```python
config = registry.get("claude")
print(config.command)   # "claude-agent-acp"
print(config.timeout)   # 120.0
```

If the name is unknown:

```python
registry.get("nonexistent")
# KeyError: "Unknown backend: 'nonexistent'. Available: ['claude', 'gemini', 'codex', 'openai', 'ollama']"
```

#### `list() -> list[str]`

Returns a list of all registered backend names.

```python
print(registry.list())
# ['claude', 'gemini', 'codex', 'openai', 'ollama', 'my-backend']
```

### Registration Timing

Because the registry is a singleton, you can register backends at module import time, in application startup hooks, or anywhere before the agent's `run()` method is called. A common pattern is to register in your application's entry point:

```python
# my_app.py
from acp_agent_framework import Agent, BackendConfig, BackendRegistry, serve

# Register custom backend at module level
BackendRegistry().register("local-llama", BackendConfig(
    command="ollama-acp",
    args=["--model", "llama3"],
    timeout=180.0,
))

agent = Agent(
    name="local-agent",
    backend="local-llama",
    instruction="You are a helpful assistant running locally.",
)

if __name__ == "__main__":
    serve(agent)
```

---

## AcpBackend Internals

The `AcpBackend` class (defined in `src/acp_agent_framework/backends/acp_backend.py`) manages the full lifecycle of a single backend subprocess. It is an internal class -- you do not instantiate it directly. The `Agent` class creates one during its `run()` method via `_get_backend()`.

### Class Structure

```python
class AcpBackend:
    def __init__(self, config: BackendConfig) -> None:
        self.config = config
        self._process: Optional[asyncio.subprocess.Process] = None
        self._connection: Optional[acp.connection.ClientSideConnection] = None
        self._client = _MinimalClient()
```

The `_MinimalClient` is a helper that implements the client-side ACP callbacks (file read/write, permission requests, terminal operations). It auto-approves permission requests and provides basic filesystem access.

### Lifecycle Methods

#### `start() -> None`

Spawns the backend process and establishes the ACP connection.

1. Constructs environment variables by merging `os.environ` with `config.env`.
2. Spawns the subprocess with `asyncio.create_subprocess_exec`, piping stdin, stdout, and stderr.
3. Creates an ACP client-side connection over the process's stdin/stdout.
4. Sends an `InitializeRequest` with protocol version and client capabilities (filesystem read/write).

```python
await backend.start()
```

If the command is not found on `$PATH`, this raises `FileNotFoundError`. If the backend process exits immediately, subsequent calls will detect `is_running == False`.

#### `new_session(cwd: str, mcp_servers: Optional[list] = None) -> str`

Creates a new ACP session with the backend. Returns the session ID string.

- `cwd` -- The working directory for the session. The backend uses this as its file operation root.
- `mcp_servers` -- Optional list of MCP server configurations for tool access.

```python
session_id = await backend.new_session("/path/to/project", mcp_servers=[])
```

Raises `RuntimeError` if `start()` has not been called.

#### `prompt(session_id: str, text: str) -> str`

Sends a prompt to the backend and returns the complete response text. This method includes retry logic (see [Retry Logic](#retry-logic)).

The prompt is sent as a `TextContentBlock` within a `PromptRequest`. The backend responds with zero or more `session_update` notifications containing text fragments, followed by a `PromptResponse`. The method collects all text fragments and joins them into a single string.

```python
response = await backend.prompt(session_id, "Explain how async/await works in Python.")
```

The call is wrapped in `asyncio.wait_for` with `config.timeout` seconds. If the backend does not respond within that window, `asyncio.TimeoutError` is raised (and caught by the retry logic).

#### `prompt_stream(session_id: str, text: str) -> AsyncGenerator[str, None]`

Sends a prompt and yields text chunks as they arrive. Unlike `prompt()`, this method does **not** include retry logic -- it is intended for streaming scenarios where partial output is acceptable.

```python
async for chunk in backend.prompt_stream(session_id, "Write a haiku."):
    print(chunk, end="", flush=True)
```

Note: In the current implementation, streaming collects all updates after the prompt completes (since ACP sends updates as notifications during prompt processing). True incremental streaming depends on the backend's update frequency.

#### `stop() -> None`

Terminates the backend process and cleans up resources.

1. Closes the ACP connection.
2. Sends `SIGTERM` to the process.
3. Waits up to 5 seconds for graceful shutdown.
4. If the process is still running after 5 seconds, sends `SIGKILL`.
5. Sets internal references to `None`.

```python
await backend.stop()
```

This method is safe to call multiple times and handles `None` process/connection gracefully.

### The `is_running` Property

```python
@property
def is_running(self) -> bool:
    return self._process is not None and self._process.returncode is None
```

Returns `True` if the subprocess has been started and has not yet exited.

### _MinimalClient Callbacks

The `_MinimalClient` class implements the ACP client interface that the backend calls back into. It handles:

| Callback            | Behavior                                                                 |
|---------------------|--------------------------------------------------------------------------|
| `session_update`    | Stores the update in an internal list for later collection               |
| `request_permission`| Auto-approves by selecting the first available option                     |
| `read_text_file`    | Reads the file from the local filesystem; raises `-32002` if not found   |
| `write_text_file`   | Writes the file to the local filesystem                                  |
| `create_terminal`   | Raises `-32601` (not supported)                                          |
| `terminal_output`   | Raises `-32601` (not supported)                                          |
| `wait_for_exit`     | Raises `-32601` (not supported)                                          |
| `kill_terminal`     | Raises `-32601` (not supported)                                          |
| `release_terminal`  | Raises `-32601` (not supported)                                          |

Terminal operations are intentionally unsupported in the framework's minimal client. If your backend requires terminal access, you would need to provide a custom client implementation.

---

## Retry Logic

The `prompt()` method implements automatic retry with exponential backoff for transient failures. This is critical for production reliability where backend processes may occasionally timeout or lose connectivity.

### Retryable Errors

The following exception types trigger a retry:

| Exception            | Typical Cause                                              |
|----------------------|------------------------------------------------------------|
| `asyncio.TimeoutError` | Backend did not respond within `config.timeout` seconds  |
| `ConnectionError`    | Pipe broken, backend process crashed mid-response          |
| `OSError`            | System-level I/O error on the subprocess pipes             |

### Backoff Formula

```
delay = retry_base_delay * (2 ^ attempt)
```

Where `attempt` is zero-indexed. With default settings (`retry_base_delay=1.0`, `max_retries=3`):

| Attempt | Delay Before Retry |
|---------|--------------------|
| 0       | (immediate, first try) |
| 1       | 1.0 seconds        |
| 2       | 2.0 seconds        |
| 3       | (no retry -- raise RuntimeError) |

With custom settings (`retry_base_delay=2.0`, `max_retries=5`):

| Attempt | Delay Before Retry |
|---------|--------------------|
| 0       | (immediate, first try) |
| 1       | 2.0 seconds        |
| 2       | 4.0 seconds        |
| 3       | 8.0 seconds        |
| 4       | 16.0 seconds       |
| 5       | (no retry -- raise RuntimeError) |

### Implementation

```python
async def prompt(self, session_id: str, text: str) -> str:
    last_error: Exception | None = None
    for attempt in range(self.config.max_retries):
        try:
            return await self._do_prompt(session_id, text)
        except (asyncio.TimeoutError, ConnectionError, OSError) as e:
            last_error = e
            if attempt < self.config.max_retries - 1:
                delay = self.config.retry_base_delay * (2 ** attempt)
                await asyncio.sleep(delay)
    raise RuntimeError(
        f"Backend prompt failed after {self.config.max_retries} attempts"
    ) from last_error
```

### Error Propagation

After exhausting all retry attempts, the method raises `RuntimeError` with the last caught exception chained via `from`. This preserves the original error context for debugging:

```
RuntimeError: Backend prompt failed after 3 attempts
  caused by: TimeoutError
```

Non-retryable errors (any exception type not in the list above) propagate immediately without retry.

---

## Serving Agents

Once you have defined an agent, you need to expose it to clients. The framework provides three ways to serve agents, each suited to different use cases.

### ACP (stdio)

The **ACP stdio transport** wraps your agent as a standard ACP-compatible process. This is the default transport and is designed for integration with editors and IDEs like Zed and VS Code that communicate with agents over stdin/stdout.

```python
from acp_agent_framework import Agent, serve

agent = Agent(
    name="code-assistant",
    backend="claude",
    instruction="You are a coding assistant specialized in Python.",
)

serve(agent)  # Default: transport="acp"
```

Explicit transport specification:

```python
serve(agent, transport="acp")
```

Under the hood, `serve()` creates a `FrameworkAgent` wrapper (defined in `src/acp_agent_framework/server/acp_server.py`) and passes it to `acp.run_agent()`. The `FrameworkAgent` implements the full ACP agent interface:

| ACP Method           | Framework Behavior                                                        |
|----------------------|---------------------------------------------------------------------------|
| `initialize`         | Returns agent capabilities (image support, embedded context)              |
| `authenticate`       | Returns empty response (no auth required by default)                      |
| `new_session`        | Creates a `Context` with a UUID session ID and the specified `cwd`        |
| `load_session`       | Looks up existing session by ID; raises `-32002` if not found             |
| `list_sessions`      | Returns all sessions, optionally filtered by `cwd`                        |
| `set_session_mode`   | Acknowledged (no-op in current implementation)                            |
| `set_session_model`  | Acknowledged (no-op in current implementation)                            |
| `set_config_option`  | Acknowledged (no-op in current implementation)                            |
| `prompt`             | Extracts text blocks, runs the agent, streams updates via notifications   |

When a prompt arrives, the `FrameworkAgent` extracts text content from the prompt blocks, sets it as the context input, runs the wrapped agent's `run()` method, and sends each `message`-type event back to the client as an ACP session update notification.

### HTTP

The **HTTP transport** exposes your agent as a REST API with Server-Sent Events (SSE) streaming. This is ideal for web applications, microservices, and any HTTP-based integration.

```python
from acp_agent_framework import Agent, serve

agent = Agent(
    name="api-assistant",
    backend="gemini",
    instruction="You are an API that answers questions concisely.",
)

serve(agent, transport="http", host="0.0.0.0", port=8000)
```

The `serve()` function with `transport="http"` creates a FastAPI application via `create_app()` (defined in `src/acp_agent_framework/server/http_server.py`) and runs it with Uvicorn.

#### Parameters

| Parameter   | Type  | Default     | Description                        |
|-------------|-------|-------------|------------------------------------|
| `transport` | `str` | `"acp"`     | Set to `"http"` for REST API mode  |
| `host`      | `str` | `"0.0.0.0"` | Network interface to bind to       |
| `port`      | `int` | `8000`      | TCP port to listen on              |

#### REST API Endpoints

##### POST /api/sessions

Creates a new session.

**Request body:**
```json
{
  "cwd": "/path/to/working/directory"
}
```

**Response (200):**
```json
{
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "cwd": "/path/to/working/directory"
}
```

The `cwd` field specifies the working directory context for the session. This is passed to the agent's `Context` and determines where file operations are rooted.

##### GET /api/sessions/{session_id}

Retrieves information about an existing session.

**Response (200):**
```json
{
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "cwd": "/path/to/working/directory"
}
```

**Response (404):**
```json
{
  "detail": "Session not found"
}
```

##### DELETE /api/sessions/{session_id}

Deletes a session and frees its resources.

**Response (200):**
```json
{
  "status": "deleted"
}
```

**Response (404):**
```json
{
  "detail": "Session not found"
}
```

##### POST /api/sessions/{session_id}/prompt

Sends a prompt to the agent and returns a Server-Sent Events (SSE) stream.

**Request body:**
```json
{
  "text": "Explain the difference between lists and tuples in Python."
}
```

**Response (200):** Content-Type `text/event-stream`

Each event is a JSON object on a `data:` line:

```
data: {"id": "evt-001", "author": "my-agent", "type": "message", "content": "Lists are mutable..."}

data: {"id": "evt-002", "author": "my-agent", "type": "stream_chunk", "content": "...additional text..."}

data: [DONE]
```

The stream terminates with `data: [DONE]` after the agent completes processing.

**Event fields:**

| Field     | Type   | Description                                                  |
|-----------|--------|--------------------------------------------------------------|
| `id`      | `str`  | Unique event identifier (UUID)                               |
| `author`  | `str`  | Name of the agent that produced this event                   |
| `type`    | `str`  | Event type: `"message"`, `"stream_chunk"`, `"error"`, etc.   |
| `content` | `str`  | The text content of the event                                |

**Response (404):**
```json
{
  "detail": "Session not found"
}
```

##### GET /

Serves the built-in web UI dashboard (see below).

##### GET /static/{path}

Serves static assets for the web UI.

#### Consuming SSE from a Client

Example using Python `httpx`:

```python
import httpx
import json

base = "http://localhost:8000"

# Create a session
resp = httpx.post(f"{base}/api/sessions", json={"cwd": "/tmp"})
session = resp.json()
session_id = session["session_id"]

# Send a prompt and consume the SSE stream
with httpx.stream(
    "POST",
    f"{base}/api/sessions/{session_id}/prompt",
    json={"text": "What is the capital of France?"},
) as response:
    for line in response.iter_lines():
        if not line.startswith("data: "):
            continue
        payload = line[6:]
        if payload == "[DONE]":
            break
        event = json.loads(payload)
        print(event["content"], end="", flush=True)
```

Example using JavaScript `fetch`:

```javascript
const res = await fetch("/api/sessions/" + sessionId + "/prompt", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ text: "Hello, agent!" }),
});

const reader = res.body.getReader();
const decoder = new TextDecoder();
let buffer = "";

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });

  const lines = buffer.split("\n");
  buffer = lines.pop();

  for (const line of lines) {
    if (!line.startsWith("data: ")) continue;
    const payload = line.slice(6);
    if (payload === "[DONE]") continue;
    const event = JSON.parse(payload);
    console.log(event.content);
  }
}
```

### Web UI Dashboard

When serving via HTTP, the framework includes a built-in web dashboard served at `GET /`. It is a single-page application built with Tailwind CSS in a dark theme.

The dashboard provides:

- **Session management** -- Create new sessions by specifying a working directory, view active sessions in the sidebar, and delete sessions.
- **Chat interface** -- A familiar chat layout with user messages on the right (blue bubbles) and agent responses on the left (gray cards with author and event type badges).
- **Real-time SSE streaming** -- Agent responses appear in real time as the SSE stream delivers events. The send button shows "Streaming..." state while a prompt is being processed.
- **Event metadata** -- Each agent event card displays the author name and event type as badges, providing visibility into multi-agent pipelines.

The dashboard is fully self-contained in a single HTML file (`src/acp_agent_framework/server/static/index.html`) with inline JavaScript and Tailwind loaded from CDN. No build step is required.

To access the dashboard, start the HTTP server and navigate to `http://localhost:8000/` in your browser:

```python
serve(agent, transport="http", port=8000)
# Dashboard available at http://localhost:8000/
```

---

## CLI

The framework includes a command-line tool `acp-agent` (installed as a console script entry point) for scaffolding and running agents without writing boilerplate.

### Commands

#### `acp-agent init <name>`

Scaffolds a new agent project directory with a template `agent.py` file.

```bash
acp-agent init my-agent
```

This creates:

```
my-agent/
  agent.py
```

The generated `agent.py` contains:

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

If the directory or file already exists, the command will not overwrite it.

#### `acp-agent run <module_path>`

Runs an agent by importing it from a Python module path. The format is `module:attribute`, where `module` is a dotted Python module path and `attribute` is the name of the agent variable in that module. If no attribute is specified, it defaults to `agent`.

**ACP stdio (default):**

```bash
acp-agent run my_agent.agent:agent
```

This imports `my_agent.agent`, gets the `agent` attribute, and serves it via ACP stdio.

**HTTP with custom port:**

```bash
acp-agent run my_agent.agent:agent --transport http --port 9000
```

Or with short flags:

```bash
acp-agent run my_agent.agent:agent -t http -p 9000
```

**Options:**

| Flag                          | Short | Default     | Description                          |
|-------------------------------|-------|-------------|--------------------------------------|
| `--transport`                 | `-t`  | `acp`       | Transport: `acp` or `http`           |
| `--host`                      |       | `0.0.0.0`   | Host to bind (HTTP only)             |
| `--port`                      | `-p`  | `8000`      | Port to bind (HTTP only)             |

**Module resolution:** The module path follows standard Python import rules. If your agent file is at `./my_project/agents/reviewer.py` with a variable named `review_agent`, you would run:

```bash
acp-agent run my_project.agents.reviewer:review_agent
```

Make sure the parent directory is on `PYTHONPATH` or you are running from the project root.

---

## Complete Examples

### Example 1: Simple Agent with Default Backend

The most minimal setup -- a single agent using the Claude backend served over ACP stdio.

```python
# agent.py
from acp_agent_framework import Agent, serve

agent = Agent(
    name="simple-assistant",
    backend="claude",
    instruction="You are a helpful coding assistant. Be concise.",
)

if __name__ == "__main__":
    serve(agent)
```

Run it:

```bash
python agent.py
# or
acp-agent run agent:agent
```

### Example 2: Custom Backend Registration

Register a custom backend with tailored timeout and retry settings, then use it in an agent.

```python
# my_app.py
from acp_agent_framework import Agent, BackendConfig, BackendRegistry, serve

# Register a custom backend
registry = BackendRegistry()
registry.register("fast-claude", BackendConfig(
    command="claude-agent-acp",
    args=[],
    env={"CLAUDE_MODEL": "claude-sonnet"},
    timeout=30.0,
    max_retries=2,
    retry_base_delay=0.5,
))

agent = Agent(
    name="fast-agent",
    backend="fast-claude",
    instruction="You are a fast, concise assistant. Keep responses under 100 words.",
)

if __name__ == "__main__":
    serve(agent, transport="http", port=8080)
```

### Example 3: HTTP Server with Multiple Endpoints

Serve an agent over HTTP with a custom working directory and consume it programmatically.

```python
# server.py
from acp_agent_framework import Agent, serve

agent = Agent(
    name="code-reviewer",
    backend="gemini",
    instruction=(
        "You are a code review assistant. When given code, provide "
        "constructive feedback on style, correctness, and performance."
    ),
    stream=True,  # Enable streaming events
)

if __name__ == "__main__":
    serve(agent, transport="http", host="127.0.0.1", port=5000)
```

```python
# client.py
import httpx
import json

base = "http://127.0.0.1:5000"

# Create session
session = httpx.post(f"{base}/api/sessions", json={"cwd": "/home/user/project"}).json()
sid = session["session_id"]
print(f"Session: {sid}")

# Send prompt
code = """
def fibonacci(n):
    if n <= 1: return n
    return fibonacci(n-1) + fibonacci(n-2)
"""

with httpx.stream(
    "POST",
    f"{base}/api/sessions/{sid}/prompt",
    json={"text": f"Review this code:\n```python\n{code}\n```"},
) as response:
    for line in response.iter_lines():
        if line.startswith("data: ") and line[6:] != "[DONE]":
            event = json.loads(line[6:])
            print(event["content"], end="")

# Clean up
httpx.delete(f"{base}/api/sessions/{sid}")
```

### Example 4: Listing and Switching Backends at Runtime

```python
from acp_agent_framework import Agent, BackendConfig, BackendRegistry

registry = BackendRegistry()

# List all available backends
print("Available backends:", registry.list())
# ['claude', 'gemini', 'codex', 'openai', 'ollama']

# Inspect a backend's configuration
claude_config = registry.get("claude")
print(f"Claude command: {claude_config.command}")
print(f"Claude timeout: {claude_config.timeout}s")

# Register a development backend with longer timeout
registry.register("claude-dev", BackendConfig(
    command="claude-agent-acp",
    timeout=600.0,  # 10 minutes for complex tasks
    max_retries=1,  # Fail fast in dev
))

# Create agents with different backends for different purposes
quick_agent = Agent(
    name="quick-helper",
    backend="claude",  # Default 120s timeout
    instruction="Answer quickly and concisely.",
)

deep_agent = Agent(
    name="deep-analyzer",
    backend="claude-dev",  # 600s timeout for thorough analysis
    instruction="Provide thorough, detailed analysis. Take your time.",
)
```

### Example 5: Agent with Tools Served via ACP

When an agent has tools, the framework automatically starts an MCP bridge subprocess that the backend can call into.

```python
# tool_agent.py
from acp_agent_framework import Agent, FunctionTool, serve

def calculate(expression: str) -> str:
    """Evaluate a mathematical expression."""
    try:
        result = eval(expression, {"__builtins__": {}})
        return str(result)
    except Exception as e:
        return f"Error: {e}"

calc_tool = FunctionTool.from_function(calculate)

agent = Agent(
    name="math-assistant",
    backend="claude",
    instruction="You are a math assistant. Use the calculate tool for arithmetic.",
    tools=[calc_tool],
)

if __name__ == "__main__":
    serve(agent)
```

The flow with tools:

1. `Agent.run()` detects `self.tools` is non-empty.
2. It creates a `McpBridge` that exposes the tools as an MCP server.
3. The MCP server configuration is passed to `backend.new_session()` via `mcp_servers`.
4. The backend can invoke the tools during prompt processing.
5. After the run completes, both the backend and the MCP bridge are stopped.

### Example 6: End-to-End CLI Workflow

```bash
# 1. Scaffold a new agent project
acp-agent init review-bot

# 2. Edit the generated agent.py to customize
cd review-bot
# (edit agent.py with your instruction and backend choice)

# 3. Run as ACP stdio (for editor integration)
acp-agent run review_bot.agent:agent

# 4. Or run as HTTP server (for web/API access)
acp-agent run review_bot.agent:agent -t http -p 3000

# 5. Open http://localhost:3000/ in a browser for the dashboard
```

---

## Architecture Summary

```
+-------------------+
|   Your Code       |
|  Agent definition |
|  serve() call     |
+--------+----------+
         |
         v
+--------+----------+     +---------------------+
|   serve()          |     |  ACP stdio transport |
|   transport="acp"  +---->|  (FrameworkAgent)    |<---> Editor/IDE
|   transport="http" |     +---------------------+
|                    |
|                    |     +---------------------+
|                    +---->|  HTTP transport      |
|                    |     |  (FastAPI + Uvicorn) |<---> Browser / API clients
+--------+----------+     |  + Web UI Dashboard  |
         |                 +---------------------+
         v
+--------+----------+
|   BackendRegistry  |  (singleton)
|   name -> config   |
+--------+----------+
         |
         v
+--------+----------+
|   AcpBackend       |
|   subprocess mgmt  |
|   retry logic      |
+--------+----------+
         |
         v (stdin/stdout JSON-RPC 2.0)
+--------+----------+
|   Backend Process  |
|   claude-agent-acp |
|   gemini --acp     |
|   npx codex-acp    |
+--------------------+
```
