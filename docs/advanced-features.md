# Advanced Features

This document provides in-depth coverage of every advanced feature in the ACP Agent Framework. Each section includes a description of the underlying mechanism, the relevant API surface, and complete runnable code examples.

---

## Table of Contents

1. [Streaming](#1-streaming)
2. [Multi-Turn Conversations](#2-multi-turn-conversations)
3. [Guardrails](#3-guardrails)
4. [Agent-to-Agent Communication](#4-agent-to-agent-communication)
5. [Observability](#5-observability)
6. [State Management](#6-state-management)
7. [Session Persistence](#7-session-persistence)
8. [Event System](#8-event-system)

---

## 1. Streaming

Streaming allows an agent to yield text incrementally as the backend produces it, rather than waiting for the entire response to complete. This is essential for interactive applications where users expect real-time feedback -- chat interfaces, CLI tools, and web UIs that display tokens as they arrive.

### How It Works

When you set `stream=True` on an `Agent`, the `run()` method changes behavior in two ways:

1. **During generation**: The agent calls `AcpBackend.prompt_stream()` instead of `AcpBackend.prompt()`. For each text chunk received via ACP session updates, the agent yields an `Event` with `type="stream_chunk"` and `content` set to that individual chunk of text.

2. **After generation completes**: All chunks are collected internally and joined into the full response string. The agent then yields a final `Event` with `type="message"` and `content` set to the complete response. This final event is identical to what a non-streaming agent would produce.

The `AcpBackend.prompt_stream()` method works by issuing a standard ACP `PromptRequest` and then iterating over the accumulated session updates, yielding each update that carries a `.text` attribute. The granularity of chunks depends on the underlying ACP agent (e.g., Claude Code typically streams token-by-token).

### API Reference

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `stream` | `bool` | `False` | Enable streaming mode on an `Agent` instance |

| Event Type | When Emitted | Content |
|------------|--------------|---------|
| `stream_chunk` | Once per text chunk during generation | A single chunk of text (may be a word, partial word, or punctuation) |
| `message` | Once after generation completes | The full concatenated response |

### Complete Example

```python
import asyncio
from acp_agent_framework import Agent, Context

async def main():
    agent = Agent(
        name="streamer",
        backend="claude",
        instruction="Write a story.",
        stream=True,
    )

    ctx = Context(session_id="s1", cwd=".")
    ctx.set_input("Tell me a short story about a robot learning to paint.")

    async for event in agent.run(ctx):
        if event.type == "stream_chunk":
            # Each chunk is a small piece of text as it arrives
            print(event.content, end="", flush=True)
        elif event.type == "message":
            # The complete response, assembled from all chunks
            print(f"\n\n--- Full response ({len(event.content)} chars) ---")
            print(event.content)

asyncio.run(main())
```

### Streaming with Error Handling

```python
import asyncio
from acp_agent_framework import Agent, Context

async def main():
    agent = Agent(
        name="streamer",
        backend="claude",
        instruction="You are a helpful assistant.",
        stream=True,
    )

    ctx = Context(session_id="s1", cwd=".")
    ctx.set_input("Explain quantum computing in simple terms.")

    chunk_count = 0
    total_chars = 0

    try:
        async for event in agent.run(ctx):
            if event.type == "stream_chunk":
                chunk_count += 1
                total_chars += len(event.content)
                print(event.content, end="", flush=True)
            elif event.type == "message":
                print(f"\n\nStreaming complete: {chunk_count} chunks, {total_chars} chars")
    except RuntimeError as e:
        print(f"Backend error during streaming: {e}")

asyncio.run(main())
```

### Non-Streaming Comparison

For comparison, here is the same agent without streaming. The `run()` method calls `AcpBackend.prompt()` (which includes retry logic with exponential backoff) and yields a single `message` event:

```python
import asyncio
from acp_agent_framework import Agent, Context

async def main():
    agent = Agent(
        name="non-streamer",
        backend="claude",
        instruction="You are a helpful assistant.",
        stream=False,  # default
    )

    ctx = Context(session_id="s1", cwd=".")
    ctx.set_input("Explain quantum computing in simple terms.")

    async for event in agent.run(ctx):
        # Only "message" events are produced when stream=False
        print(event.content)

asyncio.run(main())
```

### Key Implementation Details

- `AcpBackend.prompt()` includes retry logic (`max_retries` attempts with exponential backoff via `retry_base_delay`). `prompt_stream()` does **not** retry -- if the connection fails mid-stream, the error propagates immediately.
- Output guardrails are applied to the **complete** response after all chunks have been collected, not to individual chunks. This means a guardrail that blocks harmful content will raise `GuardrailError` after streaming finishes but before the final `message` event is yielded.
- If `output_key` is set, the complete response is stored in `ctx.state` under that key after guardrails run.

---

## 2. Multi-Turn Conversations

Multi-turn mode allows an agent to maintain conversation history across multiple calls to `run()`, enabling chatbot-like interactions where the agent remembers prior exchanges.

### How It Works

When `multi_turn=True` is set on an `Agent`:

1. **Before prompting**: The agent checks `ctx.get_history()` for existing conversation messages. If history exists, it formats each message as `"Role: content"` and appends the formatted history into the prompt sent to the backend. The prompt is assembled as: `instruction + history + current user input`, joined by double newlines.

2. **After receiving the response**: The agent calls `ctx.add_message("user", user_input)` and `ctx.add_message("assistant", response)` to record the exchange. These messages persist in the `Context` object for subsequent `run()` calls.

The conversation history lives entirely in the `Context` object. As long as you reuse the same `Context` across calls, the history accumulates. You can inspect, manipulate, or clear history at any time.

### Context History API

| Method | Signature | Description |
|--------|-----------|-------------|
| `add_message` | `add_message(role: str, content: str) -> None` | Append a message to the conversation history list |
| `get_history` | `get_history() -> list[dict[str, str]]` | Return a copy of all history entries as `{"role": ..., "content": ...}` dicts |
| `clear_history` | `clear_history() -> None` | Remove all messages from history |

### Complete Example

```python
import asyncio
from acp_agent_framework import Agent, Context

async def main():
    agent = Agent(
        name="chatbot",
        backend="claude",
        instruction="You are a friendly chatbot. Remember everything the user tells you.",
        multi_turn=True,
    )

    ctx = Context(session_id="chat-001", cwd=".")

    # Turn 1: Introduce yourself
    ctx.set_input("My name is Alice and I work as a data scientist.")
    async for event in agent.run(ctx):
        if event.type == "message":
            print(f"Bot: {event.content}")

    # Turn 2: The agent should remember the name and profession
    ctx.set_input("What's my name and what do I do?")
    async for event in agent.run(ctx):
        if event.type == "message":
            print(f"Bot: {event.content}")

    # Turn 3: Build on prior context
    ctx.set_input("What programming languages would you recommend for my job?")
    async for event in agent.run(ctx):
        if event.type == "message":
            print(f"Bot: {event.content}")

    # Inspect the accumulated history
    print(f"\nConversation history ({len(ctx.get_history())} messages):")
    for msg in ctx.get_history():
        print(f"  [{msg['role']}]: {msg['content'][:80]}...")

asyncio.run(main())
```

### Managing History

```python
import asyncio
from acp_agent_framework import Agent, Context

async def main():
    agent = Agent(
        name="chatbot",
        backend="claude",
        instruction="You are a helpful assistant.",
        multi_turn=True,
    )

    ctx = Context(session_id="chat-002", cwd=".")

    # Have a conversation
    for question in ["Hello!", "My favorite color is blue.", "What is my favorite color?"]:
        ctx.set_input(question)
        async for event in agent.run(ctx):
            if event.type == "message":
                print(f"Q: {question}")
                print(f"A: {event.content}\n")

    # Check history length
    history = ctx.get_history()
    print(f"History contains {len(history)} messages")

    # Clear history to start fresh (agent will forget everything)
    ctx.clear_history()
    print(f"After clear: {len(ctx.get_history())} messages")

    # This question will not get a correct answer since history was cleared
    ctx.set_input("What is my favorite color?")
    async for event in agent.run(ctx):
        if event.type == "message":
            print(f"After reset - A: {event.content}")

asyncio.run(main())
```

### Programmatically Injecting History

You can pre-populate history before the first `run()` call to set up a conversation context:

```python
import asyncio
from acp_agent_framework import Agent, Context

async def main():
    agent = Agent(
        name="support-bot",
        backend="claude",
        instruction="You are a technical support agent.",
        multi_turn=True,
    )

    ctx = Context(session_id="support-001", cwd=".")

    # Inject prior conversation from a database or log file
    ctx.add_message("user", "I cannot connect to the VPN.")
    ctx.add_message("assistant", "Have you tried restarting the VPN client?")
    ctx.add_message("user", "Yes, I restarted it but I still get error code 403.")

    # Continue the conversation with full context
    ctx.set_input("The error started happening after I updated my OS yesterday.")
    async for event in agent.run(ctx):
        if event.type == "message":
            print(f"Support: {event.content}")

asyncio.run(main())
```

### Key Implementation Details

- History is stored as a flat list of `{"role": str, "content": str}` dicts inside the `Context` instance.
- `get_history()` returns a **copy** of the list, so modifying the returned list does not affect the context.
- When `multi_turn=False` (the default), history is neither read nor written -- the agent is stateless between runs.
- The entire history is included in every prompt. For very long conversations, this will consume the backend's context window. You are responsible for trimming or summarizing history if it grows too large.

---

## 3. Guardrails

Guardrails are named validation and transformation functions that run on the prompt text before it reaches the backend (input guardrails) or on the response text after it comes back (output guardrails). They provide a mechanism for content filtering, secret redaction, format enforcement, and safety validation.

### How It Works

A `Guardrail` wraps a callable with signature `fn(text: str) -> Optional[str]`:

- **Return a string**: The returned string replaces the original text (transformation).
- **Return `None`**: The original text passes through unchanged (validation passed).
- **Raise `GuardrailError`**: Execution is halted. The error carries a `guardrail_name` attribute identifying which guardrail failed.

Guardrails are applied sequentially in list order. The output of one guardrail becomes the input of the next. This means transformations compose: if guardrail A redacts secrets and guardrail B lowercases text, the final text is lowercased with secrets redacted.

Input guardrails run after the full prompt is assembled (instruction + history + user input) but before it is sent to the backend. Output guardrails run on the backend response before it is stored in context or yielded as an event.

### API Reference

**`Guardrail` class:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Identifier for this guardrail (used in error reporting) |
| `fn` | `Callable[[str], Optional[str]]` | The validation/transformation function |

| Method | Signature | Description |
|--------|-----------|-------------|
| `validate` | `validate(text: str) -> str` | Run the guardrail function. Returns transformed text or original if `fn` returned `None`. Raises `GuardrailError` if `fn` raises it. |

**`GuardrailError` class:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `guardrail_name` | `str` | Name of the guardrail that raised the error |

### Complete Example: Input Redaction and Output Safety

```python
import asyncio
from acp_agent_framework import Agent, Context, Guardrail, GuardrailError

# -- Input guardrails --

def redact_api_keys(text: str) -> str:
    """Replace anything that looks like an API key with [REDACTED]."""
    import re
    return re.sub(r"(?:api[_-]?key|token|secret)[=:\s]+\S+", "[REDACTED]", text, flags=re.IGNORECASE)

def enforce_max_length(text: str) -> str | None:
    """Block prompts longer than 10,000 characters."""
    if len(text) > 10_000:
        raise GuardrailError(
            f"Input too long: {len(text)} chars (max 10,000)",
            guardrail_name="max_length",
        )
    return None  # pass through unchanged

# -- Output guardrails --

def block_harmful_content(text: str) -> str | None:
    """Block responses containing harmful instructions."""
    harmful_patterns = ["how to hack", "build a weapon", "illegal"]
    for pattern in harmful_patterns:
        if pattern in text.lower():
            raise GuardrailError(
                f"Response contained harmful content matching '{pattern}'",
                guardrail_name="harmful_content_filter",
            )
    return None  # pass through unchanged

def ensure_professional_tone(text: str) -> str | None:
    """Remove profanity from responses."""
    profanity_list = ["damn", "hell"]  # simplified example
    cleaned = text
    for word in profanity_list:
        cleaned = cleaned.replace(word, "***")
    if cleaned != text:
        return cleaned  # return transformed text
    return None  # no changes needed

async def main():
    agent = Agent(
        name="safe-agent",
        backend="claude",
        instruction="You are a professional assistant.",
        input_guardrails=[
            Guardrail("redact_secrets", redact_api_keys),
            Guardrail("max_length", enforce_max_length),
        ],
        output_guardrails=[
            Guardrail("harmful_content", block_harmful_content),
            Guardrail("professional_tone", ensure_professional_tone),
        ],
    )

    ctx = Context(session_id="s1", cwd=".")

    # This input contains an API key that will be redacted before reaching the LLM
    ctx.set_input("My api_key=sk-abc123xyz please help me configure the service.")

    try:
        async for event in agent.run(ctx):
            if event.type == "message":
                print(f"Response: {event.content}")
    except GuardrailError as e:
        print(f"Guardrail '{e.guardrail_name}' blocked execution: {e}")

asyncio.run(main())
```

### Composing Multiple Guardrails

Guardrails execute in order, each receiving the output of the previous one:

```python
from acp_agent_framework import Guardrail

def lowercase(text: str) -> str:
    return text.lower()

def strip_whitespace(text: str) -> str:
    return " ".join(text.split())

def add_prefix(text: str) -> str:
    return f"[PROCESSED] {text}"

# These compose: strip_whitespace(lowercase(text)), then add_prefix
guardrails = [
    Guardrail("lowercase", lowercase),
    Guardrail("strip", strip_whitespace),
    Guardrail("prefix", add_prefix),
]

# Manual test (without running an agent)
text = "  Hello   WORLD  "
for g in guardrails:
    text = g.validate(text)

print(text)  # "[PROCESSED] hello world"
```

### Guardrail with External Validation Service

```python
import asyncio
from acp_agent_framework import Agent, Context, Guardrail, GuardrailError

def moderation_check(text: str) -> str | None:
    """
    In production, this would call an external moderation API.
    Here we demonstrate the pattern with a simple keyword check.
    """
    blocked_categories = {
        "violence": ["kill", "attack", "destroy"],
        "personal_info": ["social security", "credit card number"],
    }

    for category, keywords in blocked_categories.items():
        for keyword in keywords:
            if keyword in text.lower():
                raise GuardrailError(
                    f"Content flagged in category '{category}' for keyword '{keyword}'",
                    guardrail_name=f"moderation_{category}",
                )
    return None

async def main():
    agent = Agent(
        name="moderated-agent",
        backend="claude",
        instruction="You are a helpful assistant.",
        output_guardrails=[Guardrail("moderation", moderation_check)],
    )

    ctx = Context(session_id="s1", cwd=".")
    ctx.set_input("Tell me a story.")

    try:
        async for event in agent.run(ctx):
            if event.type == "message":
                print(event.content)
    except GuardrailError as e:
        print(f"Blocked by {e.guardrail_name}: {e}")

asyncio.run(main())
```

### Key Implementation Details

- Input guardrails operate on the fully assembled prompt string (instruction + history + user input joined by `\n\n`).
- Output guardrails operate on the raw backend response string.
- When streaming is enabled, output guardrails run on the **concatenated** complete response, after all `stream_chunk` events have been yielded but before the final `message` event. If an output guardrail raises `GuardrailError`, the stream chunks will already have been yielded to the consumer.
- Guardrails are synchronous functions. If you need async validation (e.g., calling an external API), perform the async work outside the guardrail and capture the result in a closure.

---

## 4. Agent-to-Agent Communication

The framework supports composing agents into larger systems where one agent delegates work to another. The `AgentTool` class wraps any `BaseAgent` subclass as a tool, and `ToolAgent` provides a way to orchestrate multiple tools (including agent-backed tools) without requiring an LLM backend.

### AgentTool

`AgentTool` wraps a `BaseAgent` so it can be invoked like any other tool. When called, it:

1. Creates a fresh `Context` with session ID `agent-tool-{agent_name}`.
2. Sets the input from `args["prompt"]` (or `args["input"]`).
3. Runs the wrapped agent and collects all `message`-type events.
4. Returns the concatenated message content as a string.

**API Reference:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `run` | `run(args: dict) -> Any` | Synchronous execution (blocks until agent completes) |
| `arun` | `arun(args: dict) -> Any` | Asynchronous execution |
| `get_schema` | `get_schema() -> dict` | Returns the tool schema with `name`, `description`, and `parameters` |

The `args` dict accepts a `prompt` key (or `input` as fallback) containing the text to send to the wrapped agent.

### ToolAgent

`ToolAgent` executes tools directly without an LLM backend. You provide an async `execute` function that receives the `Context` and a dictionary of tools (keyed by tool name), runs them in whatever order you define, and returns a result string.

**Constructor Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Agent name |
| `tools` | `list[BaseTool]` | Tools available to the execute function |
| `execute` | `Callable` | Async function `(ctx, tools_dict) -> str` |
| `output_key` | `Optional[str]` | State key to store the result |

### Complete Example: Research and Summarize Pipeline

```python
import asyncio
from acp_agent_framework import Agent, AgentTool, ToolAgent, Context

async def main():
    # Define specialist agents
    researcher = Agent(
        name="researcher",
        backend="claude",
        instruction=(
            "You are a research assistant. When given a topic, provide detailed "
            "factual information with multiple perspectives. Be thorough."
        ),
    )

    summarizer = Agent(
        name="summarizer",
        backend="claude",
        instruction=(
            "You are a summarization expert. Take the provided text and create "
            "a concise summary with key bullet points. Keep it under 200 words."
        ),
    )

    # Wrap agents as tools
    research_tool = AgentTool(researcher)
    summary_tool = AgentTool(summarizer)

    # Define the orchestration logic
    async def orchestrate(ctx, tools):
        user_query = ctx.get_input()

        # Step 1: Research the topic
        research_result = await tools["researcher"].arun({"prompt": user_query})
        print(f"Research complete ({len(research_result)} chars)")

        # Step 2: Summarize the research
        summary = await tools["summarizer"].arun({
            "prompt": f"Summarize the following research:\n\n{research_result}"
        })
        print(f"Summary complete ({len(summary)} chars)")

        return summary

    # Create the orchestrator
    orchestrator = ToolAgent(
        name="orchestrator",
        tools=[research_tool, summary_tool],
        execute=orchestrate,
    )

    ctx = Context(session_id="research-001", cwd=".")
    ctx.set_input("What are the current approaches to carbon capture technology?")

    async for event in orchestrator.run(ctx):
        if event.type == "tool_result":
            print(f"\nFinal result:\n{event.content}")

asyncio.run(main())
```

### Parallel Agent Execution

```python
import asyncio
from acp_agent_framework import Agent, AgentTool, ToolAgent, Context

async def main():
    # Create multiple specialist agents
    analyst = Agent(
        name="analyst",
        backend="claude",
        instruction="Analyze the given topic from a technical perspective.",
    )

    critic = Agent(
        name="critic",
        backend="claude",
        instruction="Provide critical analysis and identify potential issues.",
    )

    writer = Agent(
        name="writer",
        backend="claude",
        instruction="Write a polished final report combining multiple analyses.",
    )

    async def parallel_then_combine(ctx, tools):
        topic = ctx.get_input()

        # Run analyst and critic in parallel
        analysis_task = tools["analyst"].arun({"prompt": topic})
        critique_task = tools["critic"].arun({"prompt": topic})
        analysis, critique = await asyncio.gather(analysis_task, critique_task)

        # Combine results with the writer
        combined_prompt = (
            f"Topic: {topic}\n\n"
            f"Technical Analysis:\n{analysis}\n\n"
            f"Critical Review:\n{critique}\n\n"
            f"Write a balanced report incorporating both perspectives."
        )
        report = await tools["writer"].arun({"prompt": combined_prompt})
        return report

    orchestrator = ToolAgent(
        name="report-generator",
        tools=[AgentTool(analyst), AgentTool(critic), AgentTool(writer)],
        execute=parallel_then_combine,
    )

    ctx = Context(session_id="report-001", cwd=".")
    ctx.set_input("The impact of large language models on software engineering")

    async for event in orchestrator.run(ctx):
        if event.type == "tool_result":
            print(event.content)

asyncio.run(main())
```

### AgentTool Schema

Each `AgentTool` exposes a schema describing its interface, which the framework uses when registering the tool with the MCP bridge:

```python
from acp_agent_framework import Agent, AgentTool

agent = Agent(
    name="helper",
    backend="claude",
    instruction="Help with tasks.",
)

tool = AgentTool(agent)
print(tool.get_schema())
# {
#     "name": "helper",
#     "description": "Delegate to helper agent",
#     "parameters": {
#         "prompt": {"type": "str", "description": "Input prompt for the agent"}
#     }
# }
```

### Key Implementation Details

- `AgentTool` creates a new `Context` for each invocation. The wrapped agent does not share state with the calling agent unless you explicitly pass data through the prompt text.
- `AgentTool.run()` (synchronous) uses `asyncio.get_event_loop().run_until_complete()`, which means it cannot be called from within an already-running event loop. Use `arun()` in async contexts.
- `ToolAgent` yields a single `Event` with `type="tool_result"` containing the string returned by the `execute` function.
- The `execute` function receives `tools` as a dict keyed by `tool.name`. Ensure each tool has a unique name.

---

## 5. Observability

The framework includes a structured JSON logging system designed for agent-specific telemetry. The `AgentLogger` class wraps Python's standard `logging` module and emits every log entry as a single-line JSON object, making it straightforward to ingest into log aggregation systems (ELK, Datadog, CloudWatch, etc.).

### How It Works

`AgentLogger` creates a namespaced Python logger under `acp_agent.{name}` with a custom `_JsonFormatter` that outputs JSON containing:

- `timestamp`: Unix timestamp (float)
- `level`: Log level string (INFO, DEBUG, ERROR, etc.)
- `agent_name`: The agent that produced the log entry (if applicable)
- `session_id`: The session identifier (if applicable)
- `message`: Human-readable log message
- Additional fields from `extra_data` (e.g., `duration_ms`, `tool_name`, `error_type`)

The log level is controlled by the `AGENT_LOG_LEVEL` environment variable. If unset, it defaults to `INFO`. Set it to `DEBUG` to see tool call and tool result entries.

### API Reference

| Method | Signature | Description |
|--------|-----------|-------------|
| `agent_start` | `agent_start(agent_name: str, session_id: str) -> None` | Log that an agent run has started |
| `agent_end` | `agent_end(agent_name: str, session_id: str, duration_ms: float) -> None` | Log agent completion with elapsed time |
| `agent_error` | `agent_error(agent_name: str, error: BaseException) -> None` | Log an error with type and message |
| `tool_call` | `tool_call(tool_name: str, args: Any) -> None` | Log a tool invocation (DEBUG level) |
| `tool_result` | `tool_result(tool_name: str, result: Any) -> None` | Log a tool result (DEBUG level) |
| `skill_loaded` | `skill_loaded(skill_name: str) -> None` | Log a skill being loaded |
| `event` | `event(event: Event) -> None` | Log an Event object with its type and author |

### Complete Example

```python
import asyncio
import time
from acp_agent_framework import Agent, Context, Event, get_logger

async def main():
    logger = get_logger("my-app")

    agent = Agent(
        name="assistant",
        backend="claude",
        instruction="You are a helpful assistant.",
    )

    ctx = Context(session_id="session-456", cwd=".")
    ctx.set_input("What is the capital of France?")

    # Log the start of the agent run
    logger.agent_start("assistant", ctx.session_id)
    start_time = time.time()

    try:
        async for event in agent.run(ctx):
            # Log each event
            logger.event(event)

            if event.type == "message":
                print(event.content)

        elapsed = (time.time() - start_time) * 1000
        logger.agent_end("assistant", ctx.session_id, duration_ms=elapsed)

    except Exception as e:
        logger.agent_error("assistant", e)
        raise

asyncio.run(main())
```

**Output (each line is a JSON object):**

```json
{"timestamp": 1709654321.123, "level": "INFO", "agent_name": "assistant", "session_id": "session-456", "message": "Agent started: assistant"}
{"timestamp": 1709654321.456, "level": "INFO", "agent_name": null, "session_id": null, "message": "Event [message] from assistant", "event_id": "abc-123", "event_type": "message", "event_author": "assistant"}
{"timestamp": 1709654321.789, "level": "INFO", "agent_name": "assistant", "session_id": "session-456", "message": "Agent finished: assistant (345.6ms)", "duration_ms": 345.6}
```

### Logging Tool Calls

Tool-level logging uses DEBUG level. Set `AGENT_LOG_LEVEL=DEBUG` to see these entries:

```python
import os
os.environ["AGENT_LOG_LEVEL"] = "DEBUG"

from acp_agent_framework import get_logger

logger = get_logger("tool-demo")

# Log a tool invocation
logger.tool_call("web_search", {"query": "ACP protocol specification", "max_results": 5})

# Log the result
logger.tool_result("web_search", "Found 5 results about ACP protocol")

# Log a skill being loaded
logger.skill_loaded("google-chat")
```

**Output:**

```json
{"timestamp": 1709654400.100, "level": "DEBUG", "agent_name": null, "session_id": null, "message": "Tool call: web_search", "tool_name": "web_search", "tool_args": {"query": "ACP protocol specification", "max_results": 5}}
{"timestamp": 1709654400.200, "level": "DEBUG", "agent_name": null, "session_id": null, "message": "Tool result: web_search", "tool_name": "web_search", "tool_result": "Found 5 results about ACP protocol"}
{"timestamp": 1709654400.300, "level": "INFO", "agent_name": null, "session_id": null, "message": "Skill loaded: google-chat", "skill_name": "google-chat"}
```

### Instrumenting an Agent Pipeline

```python
import asyncio
import time
from acp_agent_framework import Agent, AgentTool, ToolAgent, Context, get_logger

async def main():
    logger = get_logger("pipeline")

    researcher = Agent(name="researcher", backend="claude", instruction="Research topics.")
    summarizer = Agent(name="summarizer", backend="claude", instruction="Summarize text.")

    async def orchestrate(ctx, tools):
        query = ctx.get_input()

        logger.tool_call("researcher", {"prompt": query})
        t0 = time.time()
        research = await tools["researcher"].arun({"prompt": query})
        logger.tool_result("researcher", f"{len(research)} chars")
        logger.agent_end("researcher", ctx.session_id, duration_ms=(time.time() - t0) * 1000)

        logger.tool_call("summarizer", {"prompt": f"Summarize: {research[:100]}..."})
        t0 = time.time()
        summary = await tools["summarizer"].arun({"prompt": f"Summarize:\n{research}"})
        logger.tool_result("summarizer", f"{len(summary)} chars")
        logger.agent_end("summarizer", ctx.session_id, duration_ms=(time.time() - t0) * 1000)

        return summary

    pipeline = ToolAgent(
        name="pipeline",
        tools=[AgentTool(researcher), AgentTool(summarizer)],
        execute=orchestrate,
    )

    ctx = Context(session_id="pipe-001", cwd=".")
    ctx.set_input("Advances in renewable energy storage")

    logger.agent_start("pipeline", ctx.session_id)
    t_start = time.time()

    async for event in pipeline.run(ctx):
        logger.event(event)
        if event.type == "tool_result":
            print(event.content)

    logger.agent_end("pipeline", ctx.session_id, duration_ms=(time.time() - t_start) * 1000)

asyncio.run(main())
```

### Key Implementation Details

- Each `AgentLogger` instance creates its own `logging.StreamHandler` with the JSON formatter. Handlers are only added if none exist, preventing duplicate output.
- `propagate` is set to `False` to avoid duplicate entries from parent loggers.
- `tool_call` and `tool_result` log at `DEBUG` level. All other methods log at `INFO` level except `agent_error` which logs at `ERROR`.
- The `args` parameter of `tool_call` and the `result` parameter of `tool_result` are serialized via `json.dumps(default=str)`, so arbitrary objects are safely stringified.

---

## 6. State Management

The `State` class provides a key-value store with delta tracking, enabling agents to share data and track what has changed between operations. State is attached to every `Context` and is accessible throughout a pipeline.

### How It Works

`State` maintains two internal dictionaries:

- `_data`: The canonical key-value store containing all current values.
- `_delta`: Tracks keys that have been modified since the last `commit()`.

When you call `state.set(key, value)`, the value is written to both `_data` and `_delta`. When you call `state.get(key)`, it checks `_delta` first (for uncommitted changes), then falls back to `_data`. Calling `commit()` clears the delta, and `get_delta()` returns the current uncommitted changes.

### API Reference

| Method | Signature | Description |
|--------|-----------|-------------|
| `__init__` | `State(initial: Optional[dict] = None)` | Create state with optional initial values |
| `get` | `get(key: str, default: Any = None) -> Any` | Retrieve a value; checks delta first, then data |
| `set` | `set(key: str, value: Any) -> None` | Set a value in both data and delta |
| `get_delta` | `get_delta() -> dict[str, Any]` | Return a copy of all uncommitted changes |
| `commit` | `commit() -> None` | Clear the delta (mark all changes as committed) |
| `get_persistable` | `get_persistable() -> dict[str, Any]` | Return all data excluding keys prefixed with `temp:` |
| `to_dict` | `to_dict() -> dict[str, Any]` | Return a copy of all data (including temp keys) |

### Complete Example

```python
from acp_agent_framework import State

# Create state with initial values
state = State(initial={"user_name": "Alice", "language": "en"})

# Read values
print(state.get("user_name"))          # "Alice"
print(state.get("missing_key"))        # None
print(state.get("missing_key", "N/A")) # "N/A"

# Set new values
state.set("result", "computation done")
state.set("score", 0.95)

# Check what has changed since creation (or last commit)
print(state.get_delta())
# {"result": "computation done", "score": 0.95}

# Commit clears the delta
state.commit()
print(state.get_delta())  # {}

# Values are still in state after commit
print(state.get("result"))  # "computation done"

# Make more changes
state.set("score", 0.99)
print(state.get_delta())  # {"score": 0.99}
```

### Temporary Values

Keys prefixed with `temp:` are excluded from `get_persistable()`, which is used by the session persistence layer. This is useful for caching intermediate results that should not survive a save/load cycle:

```python
from acp_agent_framework import State

state = State()

# Persistent data
state.set("final_answer", "42")
state.set("model_version", "v2.1")

# Temporary data (not persisted)
state.set("temp:raw_response", "very large raw text...")
state.set("temp:cache_hit", True)

# Only non-temp keys are persisted
persistable = state.get_persistable()
print(persistable)
# {"final_answer": "42", "model_version": "v2.1"}

# to_dict() includes everything
print(state.to_dict())
# {"final_answer": "42", "model_version": "v2.1", "temp:raw_response": "very large raw text...", "temp:cache_hit": True}
```

### State in Agent Pipelines

When using `output_key` on an `Agent` or `ToolAgent`, the result is automatically stored in `ctx.state`:

```python
import asyncio
from acp_agent_framework import Agent, SequentialAgent, Context, State

async def main():
    step1 = Agent(
        name="analyzer",
        backend="claude",
        instruction="Analyze the given text and list key themes.",
        output_key="themes",
    )

    step2 = Agent(
        name="expander",
        backend="claude",
        instruction=lambda ctx: (
            f"Expand on these themes: {ctx.state.get('themes', 'none')}"
        ),
        output_key="expanded",
    )

    pipeline = SequentialAgent(
        name="analysis-pipeline",
        sub_agents=[step1, step2],
    )

    # Start with shared state
    shared_state = State(initial={"document_id": "doc-123"})
    ctx = Context(session_id="s1", cwd=".", state=shared_state)
    ctx.set_input("The rise of electric vehicles and their impact on urban planning.")

    async for event in pipeline.run(ctx):
        if event.type == "message":
            print(f"[{event.author}]: {event.content[:100]}...")

    # State now contains outputs from both steps
    print(f"\nStored keys: {list(ctx.state.to_dict().keys())}")
    # ["document_id", "themes", "expanded"]

asyncio.run(main())
```

### Delta Tracking for Event Actions

The delta mechanism integrates with the event system. You can capture uncommitted state changes and attach them to an event:

```python
from acp_agent_framework import State, Event, EventActions

state = State()
state.set("step", "complete")
state.set("confidence", 0.92)

# Capture the delta as an event action
delta = state.get_delta()
event = Event(
    author="my-agent",
    type="message",
    content="Analysis complete.",
    actions=EventActions(state_delta=delta),
)

print(event.actions.state_delta)
# {"step": "complete", "confidence": 0.92}

# Commit after capturing
state.commit()
```

---

## 7. Session Persistence

The `JsonSessionStore` provides file-based persistence for session data, enabling agents to save and restore state across process restarts. Sessions are stored as individual JSON files in a configurable directory.

### How It Works

Each session is saved as `{session_id}.json` inside a storage directory. The store handles directory creation automatically. Data is serialized with `json.dumps(default=str)`, so datetime objects, UUIDs, and other common types are safely stringified.

### API Reference

| Method | Signature | Description |
|--------|-----------|-------------|
| `__init__` | `JsonSessionStore(storage_dir: Path)` | Create a store; directory is created if it does not exist |
| `save` | `save(session_id: str, data: dict) -> None` | Write session data to disk |
| `load` | `load(session_id: str) -> Optional[dict]` | Read session data; returns `None` if session does not exist |
| `delete` | `delete(session_id: str) -> None` | Remove the session file from disk |
| `list_sessions` | `list_sessions() -> list[str]` | Return all stored session IDs |

### Complete Example

```python
from pathlib import Path
from acp_agent_framework.persistence import JsonSessionStore
from acp_agent_framework import State, Context

# Create a store in a local directory
store = JsonSessionStore(Path("./sessions"))

# Save session state
ctx = Context(session_id="user-alice-001", cwd=".")
ctx.state.set("preferences", {"theme": "dark", "language": "en"})
ctx.state.set("last_query", "What is machine learning?")
ctx.state.set("temp:cache", "ephemeral data")

# Persist only non-temp state
store.save(ctx.session_id, ctx.state.get_persistable())

# Later (possibly in a new process), restore the session
loaded = store.load("user-alice-001")
if loaded:
    restored_state = State(initial=loaded)
    new_ctx = Context(session_id="user-alice-001", cwd=".", state=restored_state)
    print(new_ctx.state.get("preferences"))  # {"theme": "dark", "language": "en"}
    print(new_ctx.state.get("last_query"))   # "What is machine learning?"
    print(new_ctx.state.get("temp:cache"))   # None (was not persisted)
```

### Session Management

```python
from pathlib import Path
from acp_agent_framework.persistence import JsonSessionStore

store = JsonSessionStore(Path("./sessions"))

# Save multiple sessions
store.save("session-001", {"user": "alice", "turns": 5})
store.save("session-002", {"user": "bob", "turns": 3})
store.save("session-003", {"user": "charlie", "turns": 1})

# List all sessions
sessions = store.list_sessions()
print(sessions)  # ["session-001", "session-002", "session-003"]

# Delete a specific session
store.delete("session-002")

# Verify deletion
print(store.load("session-002"))  # None
print(store.list_sessions())  # ["session-001", "session-003"]
```

### Persisting Conversation History

To save multi-turn conversation history alongside state:

```python
import asyncio
from pathlib import Path
from acp_agent_framework import Agent, Context, State
from acp_agent_framework.persistence import JsonSessionStore

store = JsonSessionStore(Path("./sessions"))

async def chat_session():
    agent = Agent(
        name="chatbot",
        backend="claude",
        instruction="You are a helpful assistant.",
        multi_turn=True,
    )

    # Try to restore a previous session
    session_id = "chat-alice"
    saved = store.load(session_id)

    if saved:
        state = State(initial=saved.get("state", {}))
        ctx = Context(session_id=session_id, cwd=".", state=state)
        # Restore conversation history
        for msg in saved.get("history", []):
            ctx.add_message(msg["role"], msg["content"])
        print(f"Restored session with {len(ctx.get_history())} messages")
    else:
        ctx = Context(session_id=session_id, cwd=".")
        print("Starting new session")

    # Have a conversation turn
    ctx.set_input("What were we talking about?")
    async for event in agent.run(ctx):
        if event.type == "message":
            print(f"Bot: {event.content}")

    # Save session (state + history)
    store.save(session_id, {
        "state": ctx.state.get_persistable(),
        "history": ctx.get_history(),
    })
    print(f"Session saved with {len(ctx.get_history())} messages")

asyncio.run(chat_session())
```

### Key Implementation Details

- Files are stored as `{storage_dir}/{session_id}.json`.
- `save()` overwrites any existing session file with the same ID.
- `load()` returns `None` (not an empty dict) if the session file does not exist.
- `list_sessions()` returns session IDs (file stems) by globbing `*.json` in the storage directory.
- `json.dumps(default=str)` is used for serialization, so non-JSON-serializable objects are converted to strings rather than raising errors. Be aware that this conversion is lossy -- a `datetime` object becomes a string and will not be automatically deserialized back to `datetime`.

---

## 8. Event System

The `Event` and `EventActions` classes form the communication backbone of the framework. Every agent yields `Event` objects from its `run()` method, and consumers (other agents, pipelines, or application code) process these events to extract results, trigger side effects, or coordinate workflows.

### Event Class

`Event` is a Pydantic `BaseModel` with the following fields:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | Auto-generated UUID | Unique identifier for this event |
| `author` | `str` | Required | Name of the agent that produced this event |
| `type` | `str` | Required | Event category (see table below) |
| `content` | `Any` | Required | The payload -- typically a string but can be any serializable value |
| `timestamp` | `float` | `time.time()` | Unix timestamp of when the event was created |
| `actions` | `Optional[EventActions]` | `None` | Optional structured side effects |

### Event Types

| Type | Producer | Description |
|------|----------|-------------|
| `message` | `Agent` | Complete LLM response (always the final event from a non-streaming agent, or the closing event from a streaming agent) |
| `stream_chunk` | `Agent` (streaming) | Individual text chunk during streaming |
| `tool_result` | `ToolAgent` | Result of tool execution |

### EventActions Class

`EventActions` carries structured side-effect instructions alongside an event:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `state_delta` | `dict[str, Any]` | `{}` | Key-value pairs to merge into state |
| `transfer_to_agent` | `Optional[str]` | `None` | Name of an agent to transfer control to |
| `escalate` | `Optional[bool]` | `None` | Flag indicating the event should be escalated to a parent agent or human operator |

### Complete Example: Creating and Inspecting Events

```python
import time
from acp_agent_framework import Event, EventActions

# Simple message event
message_event = Event(
    author="assistant",
    type="message",
    content="The capital of France is Paris.",
)

print(f"Event ID: {message_event.id}")
print(f"Author: {message_event.author}")
print(f"Type: {message_event.type}")
print(f"Content: {message_event.content}")
print(f"Timestamp: {message_event.timestamp}")
print(f"Actions: {message_event.actions}")
```

### Events with Actions

```python
from acp_agent_framework import Event, EventActions

# Event that updates state
update_event = Event(
    author="data-processor",
    type="tool_result",
    content="Processing complete.",
    actions=EventActions(
        state_delta={
            "processed_count": 42,
            "status": "complete",
            "last_processed_at": "2025-01-15T10:30:00Z",
        },
    ),
)

# Event that requests transfer to another agent
transfer_event = Event(
    author="triage-agent",
    type="message",
    content="This question requires a specialist.",
    actions=EventActions(
        transfer_to_agent="specialist-agent",
    ),
)

# Event that requests human escalation
escalation_event = Event(
    author="support-bot",
    type="message",
    content="I cannot resolve this issue automatically.",
    actions=EventActions(
        escalate=True,
        state_delta={"escalation_reason": "unresolvable_error"},
    ),
)
```

### Processing Events in Application Code

```python
import asyncio
from acp_agent_framework import Agent, Context, Event

async def process_events(agent: Agent, ctx: Context):
    """Process events from an agent run with full event handling."""
    async for event in agent.run(ctx):
        # Handle by event type
        if event.type == "stream_chunk":
            print(event.content, end="", flush=True)

        elif event.type == "message":
            print(f"\n[{event.author}] {event.content}")

        elif event.type == "tool_result":
            print(f"[Tool Result from {event.author}] {event.content}")

        # Handle actions if present
        if event.actions:
            if event.actions.state_delta:
                for key, value in event.actions.state_delta.items():
                    ctx.state.set(key, value)
                    print(f"  State updated: {key} = {value}")

            if event.actions.transfer_to_agent:
                print(f"  Transfer requested to: {event.actions.transfer_to_agent}")

            if event.actions.escalate:
                print(f"  Escalation requested by {event.author}")

async def main():
    agent = Agent(
        name="assistant",
        backend="claude",
        instruction="You are a helpful assistant.",
    )

    ctx = Context(session_id="s1", cwd=".")
    ctx.set_input("Hello, how are you?")

    await process_events(agent, ctx)

asyncio.run(main())
```

### Event Serialization

Since `Event` is a Pydantic model, it supports standard serialization:

```python
import json
from acp_agent_framework import Event, EventActions

event = Event(
    author="my-agent",
    type="message",
    content="Hello, world!",
    actions=EventActions(
        state_delta={"key": "value"},
        transfer_to_agent="other-agent",
        escalate=True,
    ),
)

# Serialize to dict
event_dict = event.model_dump()
print(json.dumps(event_dict, indent=2, default=str))

# Reconstruct from dict
reconstructed = Event.model_validate(event_dict)
assert reconstructed.id == event.id
assert reconstructed.content == event.content
assert reconstructed.actions.transfer_to_agent == "other-agent"
```

### Key Implementation Details

- `Event.id` is auto-generated as a UUID v4 string. You can override it by passing `id="custom-id"` to the constructor.
- `Event.timestamp` defaults to `time.time()` at construction. It is not updated if the event object is reused.
- `EventActions.state_delta` defaults to an empty dict, not `None`. This means `event.actions.state_delta` is always safe to iterate over if `actions` is not `None`.
- Events are yielded from `run()` as an `AsyncGenerator[Event, None]`. You must consume them with `async for` -- they cannot be awaited directly.
- The `actions` field is entirely advisory. The framework does not automatically apply `state_delta` or honor `transfer_to_agent` -- it is up to the consuming code (or a higher-level orchestrator like `RouterAgent`) to interpret and act on these fields.
