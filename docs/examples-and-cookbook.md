# ACP Agent Framework: Examples and Cookbook

A comprehensive collection of runnable examples covering every major feature of the ACP Agent Framework. Each example includes full imports, setup, and descriptions of expected output.

---

## Table of Contents

1. [Simple Q&A Agent](#1-simple-qa-agent)
2. [Research Pipeline (Sequential Agent Chain)](#2-research-pipeline-sequential-agent-chain)
3. [Smart Router (Route to Specialists)](#3-smart-router-route-to-specialists)
4. [Tool-Augmented Agent](#4-tool-augmented-agent)
5. [Chat Bot with Memory (Multi-Turn Conversation)](#5-chat-bot-with-memory-multi-turn-conversation)
6. [Agent Orchestration (Agents Calling Agents)](#6-agent-orchestration-agents-calling-agents)
7. [Secure Agent with Guardrails](#7-secure-agent-with-guardrails)
8. [Streaming Agent (Real-Time Output)](#8-streaming-agent-real-time-output)
9. [Google Chat Agent (Using Skills)](#9-google-chat-agent-using-skills)
10. [Full Production Setup (HTTP Server with Logging)](#10-full-production-setup-http-server-with-logging)
11. [Custom Agent Type (Subclassing BaseAgent)](#11-custom-agent-type-subclassing-baseagent)
12. [Testing Agents (Unit Tests)](#12-testing-agents-unit-tests)

---

## Prerequisites

Install the framework:

```bash
pip install -e .
```

For examples that use an LLM backend (e.g., `backend="claude"`), you need the corresponding ACP agent binary installed and available on your PATH. For example, `claude-agent-acp` for the Claude backend. Examples that do not require a live backend are marked accordingly and use `ToolAgent` or mock objects.

---

## 1. Simple Q&A Agent

A minimal agent that sends a single question to an LLM backend and prints the response.

**Requirements:** A working ACP backend (e.g., `claude-agent-acp` on PATH).

```python
"""simple_qa.py - Minimal Q&A agent."""
import asyncio
from acp_agent_framework import Agent, Context

agent = Agent(
    name="qa",
    backend="claude",
    instruction="Answer questions concisely in one or two sentences.",
)


async def main():
    ctx = Context(session_id="s1", cwd=".")
    ctx.set_input("What is Python?")

    async for event in agent.run(ctx):
        print(f"[{event.type}] {event.content}")

    # The final output is also stored on the context:
    print(f"\nFinal output: {ctx.get_output()}")


asyncio.run(main())
```

**Expected output:**

```
[message] Python is a high-level, interpreted programming language known for its readability and versatility.

Final output: Python is a high-level, interpreted programming language known for its readability and versatility.
```

### Variant: No-Backend Version Using ToolAgent

If you do not have a backend available, you can use `ToolAgent` to simulate the same pattern without any LLM calls:

```python
"""simple_qa_no_backend.py - Q&A without an LLM backend."""
import asyncio
from acp_agent_framework import ToolAgent, Context


async def answer_question(ctx, tools):
    """Hardcoded answers for demonstration purposes."""
    question = ctx.get_input() or ""
    answers = {
        "python": "Python is a high-level, interpreted programming language.",
        "rust": "Rust is a systems programming language focused on safety.",
    }
    question_lower = question.lower()
    for keyword, answer in answers.items():
        if keyword in question_lower:
            return answer
    return "I don't know the answer to that question."


agent = ToolAgent(
    name="qa",
    execute=answer_question,
)


async def main():
    ctx = Context(session_id="s1", cwd=".")
    ctx.set_input("What is Python?")

    async for event in agent.run(ctx):
        print(f"[{event.type}] {event.content}")


asyncio.run(main())
```

**Expected output:**

```
[tool_result] Python is a high-level, interpreted programming language.
```

---

## 2. Research Pipeline (Sequential Agent Chain)

A three-agent pipeline where each agent processes the output of the previous one. The `SequentialAgent` runs sub-agents in order. Each agent stores its output via `output_key`, and the next agent reads from shared state.

**Requirements:** A working ACP backend for the LLM version. The no-backend version below runs standalone.

### No-Backend Version (ToolAgent Pipeline)

```python
"""research_pipeline.py - Sequential pipeline: researcher -> writer -> reviewer."""
import asyncio
from acp_agent_framework import ToolAgent, SequentialAgent, Context, State


async def research(ctx, tools):
    """Simulate research by producing bullet points."""
    topic = ctx.get_input() or "unknown topic"
    findings = (
        f"Research findings on '{topic}':\n"
        f"- Finding 1: {topic} was first developed in the early 2000s.\n"
        f"- Finding 2: It is widely used in enterprise environments.\n"
        f"- Finding 3: The community has grown to over 1 million developers."
    )
    return findings


async def write_article(ctx, tools):
    """Transform research findings into a polished article."""
    research_data = ctx.state.get("research_output", "No research available.")
    article = (
        f"Article Draft\n"
        f"=============\n\n"
        f"Based on our research, here is a summary:\n\n"
        f"{research_data}\n\n"
        f"In conclusion, this topic continues to evolve rapidly."
    )
    return article


async def review_article(ctx, tools):
    """Review the article and provide feedback."""
    draft = ctx.state.get("article_draft", "No draft available.")
    review = (
        f"Review Report\n"
        f"=============\n\n"
        f"Draft length: {len(draft)} characters\n"
        f"Quality: APPROVED\n"
        f"Notes: The article covers the key points adequately.\n\n"
        f"--- Final Article ---\n{draft}"
    )
    return review


researcher = ToolAgent(name="researcher", execute=research, output_key="research_output")
writer = ToolAgent(name="writer", execute=write_article, output_key="article_draft")
reviewer = ToolAgent(name="reviewer", execute=review_article, output_key="review_result")

pipeline = SequentialAgent(
    name="research-pipeline",
    agents=[researcher, writer, reviewer],
)


async def main():
    ctx = Context(session_id="pipeline-1", cwd=".")
    ctx.set_input("Kubernetes")

    async for event in pipeline.run(ctx):
        print(f"[{event.author}] {event.content}\n")

    # Inspect state after pipeline completes:
    print("--- State Keys ---")
    print(f"research_output: {ctx.state.get('research_output')[:50]}...")
    print(f"article_draft: {ctx.state.get('article_draft')[:50]}...")
    print(f"review_result: {ctx.state.get('review_result')[:50]}...")


asyncio.run(main())
```

**Expected output:**

Three `[tool_result]` events are printed, one per agent. The state dictionary holds all intermediate outputs accessible by key. Each subsequent agent reads from the state populated by the previous agent.

### LLM-Backed Version

```python
"""research_pipeline_llm.py - Sequential pipeline with real LLM backends."""
import asyncio
from acp_agent_framework import Agent, SequentialAgent, Context


researcher = Agent(
    name="researcher",
    backend="claude",
    instruction=(
        "You are a research analyst. Given a topic, produce 5 bullet points "
        "of key facts. Output only the bullet points, nothing else."
    ),
    output_key="research_output",
)

writer = Agent(
    name="writer",
    backend="claude",
    instruction=lambda ctx: (
        "You are a technical writer. Using these research findings, write a "
        "concise 3-paragraph article:\n\n"
        f"{ctx.state.get('research_output', 'No research available.')}"
    ),
    output_key="article_draft",
)

reviewer = Agent(
    name="reviewer",
    backend="claude",
    instruction=lambda ctx: (
        "You are an editor. Review this article draft and provide a final "
        "polished version with any corrections:\n\n"
        f"{ctx.state.get('article_draft', 'No draft available.')}"
    ),
    output_key="final_article",
)

pipeline = SequentialAgent(
    name="research-pipeline",
    agents=[researcher, writer, reviewer],
)


async def main():
    ctx = Context(session_id="pipeline-llm-1", cwd=".")
    ctx.set_input("WebAssembly")

    async for event in pipeline.run(ctx):
        print(f"[{event.author}] {event.content}\n")


asyncio.run(main())
```

**Key points:**
- The `instruction` parameter accepts either a string or a callable (`Callable[[Context], str]`). Using a callable lets you dynamically inject state from previous agents.
- `output_key` stores the agent's response in `ctx.state` so downstream agents can access it.

---

## 3. Smart Router (Route to Specialists)

A `RouterAgent` inspects the user input for keywords and dispatches to the appropriate specialist agent. If no route matches, a `default_agent` handles the request.

```python
"""smart_router.py - Route questions to specialist agents."""
import asyncio
from acp_agent_framework import ToolAgent, RouterAgent, Route, Context


async def handle_code(ctx, tools):
    question = ctx.get_input() or ""
    return f"[Code Expert] Here is help with your code question: '{question}'"


async def handle_writing(ctx, tools):
    question = ctx.get_input() or ""
    return f"[Writing Expert] Here is help with your writing question: '{question}'"


async def handle_math(ctx, tools):
    question = ctx.get_input() or ""
    # Simple eval for demonstration (never do this in production)
    try:
        # Extract a simple expression if present
        import re
        match = re.search(r"[\d+\-*/().]+", question)
        if match:
            result = eval(match.group())  # noqa: S307
            return f"[Math Expert] The answer is: {result}"
    except Exception:
        pass
    return f"[Math Expert] I can help with math. Please provide an expression."


async def handle_default(ctx, tools):
    question = ctx.get_input() or ""
    return f"[General Assistant] I received: '{question}'. How can I help?"


code_agent = ToolAgent(name="code-agent", execute=handle_code, description="Handles code questions")
writing_agent = ToolAgent(name="writing-agent", execute=handle_writing, description="Handles writing questions")
math_agent = ToolAgent(name="math-agent", execute=handle_math, description="Handles math questions")
default_agent = ToolAgent(name="default-agent", execute=handle_default, description="Fallback")

router = RouterAgent(
    name="smart-router",
    routes=[
        Route(keywords=["code", "python", "javascript", "function", "bug", "debug"], agent=code_agent),
        Route(keywords=["write", "essay", "article", "grammar", "proofread"], agent=writing_agent),
        Route(keywords=["math", "calculate", "sum", "multiply", "equation"], agent=math_agent),
    ],
    default_agent=default_agent,
)


async def main():
    test_inputs = [
        "How do I fix this Python bug?",
        "Write me an essay about climate change.",
        "Calculate 42 * 17",
        "What is the weather today?",
    ]

    for user_input in test_inputs:
        ctx = Context(session_id="router-test", cwd=".")
        ctx.set_input(user_input)

        print(f"Input: {user_input}")
        async for event in router.run(ctx):
            print(f"  -> {event.content}")
        print()


asyncio.run(main())
```

**Expected output:**

```
Input: How do I fix this Python bug?
  -> [Code Expert] Here is help with your code question: 'How do I fix this Python bug?'

Input: Write me an essay about climate change.
  -> [Writing Expert] Here is help with your writing question: 'Write me an essay about climate change.'

Input: Calculate 42 * 17
  -> [Math Expert] The answer is: 714

Input: What is the weather today?
  -> [General Assistant] I received: 'What is the weather today?'. How can I help?
```

**How routing works:** The `RouterAgent._find_route()` method lowercases the input and checks each route's keywords list. The first route with a matching keyword wins. If none match, the `default_agent` is used. If `default_agent` is also `None`, a message event with "No matching route found for input." is yielded.

---

## 4. Tool-Augmented Agent

### 4a. Using FunctionTool with ToolAgent (No Backend Required)

`FunctionTool` wraps any Python callable into a tool with auto-extracted schema. `ToolAgent` executes tools directly via a user-defined `execute` function -- no LLM backend needed.

```python
"""tool_augmented.py - Agent with calculator, search, and file reader tools."""
import asyncio
import math
from pathlib import Path
from acp_agent_framework import FunctionTool, ToolAgent, Context


# -- Define tools as plain Python functions --

def calculator(expression: str) -> str:
    """Evaluate a mathematical expression and return the result."""
    # Restricted eval with math module only
    allowed_names = {k: v for k, v in math.__dict__.items() if not k.startswith("_")}
    allowed_names["abs"] = abs
    allowed_names["round"] = round
    try:
        result = eval(expression, {"__builtins__": {}}, allowed_names)  # noqa: S307
        return f"Result: {result}"
    except Exception as e:
        return f"Error evaluating '{expression}': {e}"


def web_search(query: str) -> str:
    """Search the web for information (simulated)."""
    # In production, integrate with a real search API
    mock_results = {
        "python": "Python is a programming language created by Guido van Rossum.",
        "kubernetes": "Kubernetes is a container orchestration platform by Google.",
        "terraform": "Terraform is an IaC tool by HashiCorp.",
    }
    query_lower = query.lower()
    for keyword, result in mock_results.items():
        if keyword in query_lower:
            return f"Search result: {result}"
    return f"No results found for '{query}'."


def read_file(filepath: str) -> str:
    """Read the contents of a file and return them."""
    path = Path(filepath)
    if not path.exists():
        return f"File not found: {filepath}"
    if not path.is_file():
        return f"Not a file: {filepath}"
    try:
        content = path.read_text(encoding="utf-8")
        # Truncate large files for display
        if len(content) > 2000:
            return content[:2000] + f"\n... (truncated, {len(content)} total chars)"
        return content
    except Exception as e:
        return f"Error reading file: {e}"


# -- Wrap functions as FunctionTool objects --

calc_tool = FunctionTool(calculator)
search_tool = FunctionTool(web_search)
file_tool = FunctionTool(read_file)


# -- Inspect auto-generated schemas --

def show_schemas():
    for tool in [calc_tool, search_tool, file_tool]:
        schema = tool.get_schema()
        print(f"Tool: {schema['name']}")
        print(f"  Description: {schema['description']}")
        print(f"  Parameters: {schema['parameters']}")
        print()


# -- Define the execute function that decides which tool to call --

async def execute_with_tools(ctx, tools):
    """Parse the user input and dispatch to the right tool."""
    user_input = ctx.get_input() or ""

    if user_input.startswith("calc:"):
        expression = user_input[5:].strip()
        return tools["calculator"].run({"expression": expression})

    elif user_input.startswith("search:"):
        query = user_input[7:].strip()
        return tools["web_search"].run({"query": query})

    elif user_input.startswith("read:"):
        filepath = user_input[5:].strip()
        return tools["read_file"].run({"filepath": filepath})

    else:
        return (
            "Unknown command. Use one of:\n"
            "  calc:<expression>    - Evaluate math\n"
            "  search:<query>       - Search the web\n"
            "  read:<filepath>      - Read a file"
        )


agent = ToolAgent(
    name="tool-agent",
    tools=[calc_tool, search_tool, file_tool],
    execute=execute_with_tools,
)


async def main():
    show_schemas()

    test_inputs = [
        "calc: 2**10 + math.sqrt(144)",
        "search: What is Kubernetes?",
        "read: /etc/hostname",
        "hello",
    ]

    for user_input in test_inputs:
        ctx = Context(session_id="tools-1", cwd=".")
        ctx.set_input(user_input)

        print(f"Input: {user_input}")
        async for event in agent.run(ctx):
            print(f"  -> {event.content}")
        print()


asyncio.run(main())
```

**Expected output:**

```
Tool: calculator
  Description: Evaluate a mathematical expression and return the result.
  Parameters: {'expression': {'type': 'str'}}

Tool: web_search
  Description: Search the web for information (simulated).
  Parameters: {'query': {'type': 'str'}}

Tool: read_file
  Description: Read the contents of a file and return them.
  Parameters: {'filepath': {'type': 'str'}}

Input: calc: 2**10 + math.sqrt(144)
  -> Result: 1036.0

Input: search: What is Kubernetes?
  -> Search result: Kubernetes is a container orchestration platform by Google.

Input: read: /etc/hostname
  -> <contents of /etc/hostname or "File not found">

Input: hello
  -> Unknown command. Use one of:
  calc:<expression>    - Evaluate math
  search:<query>       - Search the web
  read:<filepath>      - Read a file
```

### 4b. Using FunctionTool with Agent (LLM Backend)

When tools are attached to an `Agent` (not `ToolAgent`), they are exposed to the LLM backend via the MCP bridge. The LLM decides when and how to call them.

```python
"""tool_augmented_llm.py - LLM agent with tools exposed via MCP bridge."""
import asyncio
from acp_agent_framework import Agent, FunctionTool, Context


def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    # Simulated response
    return f"Weather in {city}: 72F, partly cloudy."


def get_stock_price(ticker: str) -> str:
    """Get the current stock price for a ticker symbol."""
    mock_prices = {"AAPL": 185.42, "GOOGL": 141.80, "MSFT": 420.55}
    price = mock_prices.get(ticker.upper())
    if price:
        return f"{ticker.upper()}: ${price}"
    return f"Unknown ticker: {ticker}"


weather_tool = FunctionTool(get_weather)
stock_tool = FunctionTool(get_stock_price)

agent = Agent(
    name="assistant",
    backend="claude",
    instruction=(
        "You are a helpful assistant with access to weather and stock tools. "
        "Use the appropriate tool when the user asks about weather or stocks."
    ),
    tools=[weather_tool, stock_tool],
)


async def main():
    ctx = Context(session_id="tools-llm-1", cwd=".")
    ctx.set_input("What is the weather in San Francisco and what is Apple's stock price?")

    async for event in agent.run(ctx):
        print(f"[{event.author}] {event.content}")


asyncio.run(main())
```

**Key points:**
- The `Agent` class creates an `McpBridge` from the tools list, which serializes tool definitions into a temp file and spawns an MCP server subprocess.
- The ACP backend (e.g., Claude) receives the MCP server configuration and can call tools during its reasoning loop.
- The bridge is automatically cleaned up when the agent finishes.

### 4c. Async Tools

`FunctionTool` supports async functions. Use `arun()` instead of `run()` to invoke them:

```python
"""async_tools.py - Tools with async functions."""
import asyncio
from acp_agent_framework import FunctionTool, ToolAgent, Context


async def fetch_data(url: str) -> str:
    """Fetch data from a URL (simulated async I/O)."""
    await asyncio.sleep(0.1)  # Simulate network delay
    return f"Response from {url}: {{\"status\": \"ok\", \"data\": [1, 2, 3]}}"


fetch_tool = FunctionTool(fetch_data)


async def execute(ctx, tools):
    url = ctx.get_input() or "https://api.example.com/data"
    # Use arun() for async tools
    result = await tools["fetch_data"].arun({"url": url})
    return result


agent = ToolAgent(name="async-agent", tools=[fetch_tool], execute=execute)


async def main():
    ctx = Context(session_id="async-1", cwd=".")
    ctx.set_input("https://api.example.com/users")

    async for event in agent.run(ctx):
        print(event.content)


asyncio.run(main())
```

**Expected output:**

```
Response from https://api.example.com/users: {"status": "ok", "data": [1, 2, 3]}
```

---

## 5. Chat Bot with Memory (Multi-Turn Conversation)

The `Agent` class supports multi-turn conversations when `multi_turn=True`. The `Context` object tracks conversation history, and all messages are prepended to the prompt on each turn.

**Requirements:** A working ACP backend.

```python
"""chatbot_memory.py - Multi-turn conversation with history tracking."""
import asyncio
from acp_agent_framework import Agent, Context


agent = Agent(
    name="chatbot",
    backend="claude",
    instruction=(
        "You are a friendly conversational assistant. Remember what the user "
        "has said in previous messages and refer back to it when relevant. "
        "Keep responses brief."
    ),
    multi_turn=True,
)


async def chat(ctx, message):
    """Send a message and collect the response."""
    ctx.set_input(message)
    response_text = ""
    async for event in agent.run(ctx):
        if event.type == "message":
            response_text = event.content
    return response_text


async def main():
    # Create a single context that persists across turns
    ctx = Context(session_id="chat-session-1", cwd=".")

    # Turn 1
    reply = await chat(ctx, "Hi, my name is Sanjay.")
    print(f"User: Hi, my name is Sanjay.")
    print(f"Bot:  {reply}\n")

    # Turn 2
    reply = await chat(ctx, "I work as a platform engineer.")
    print(f"User: I work as a platform engineer.")
    print(f"Bot:  {reply}\n")

    # Turn 3 - The bot should remember the name and occupation
    reply = await chat(ctx, "What do you know about me?")
    print(f"User: What do you know about me?")
    print(f"Bot:  {reply}\n")

    # Inspect conversation history
    print("--- Conversation History ---")
    for msg in ctx.get_history():
        print(f"  [{msg['role']}] {msg['content'][:80]}...")


asyncio.run(main())
```

**Expected behavior:**

- Turn 3 should reference "Sanjay" and "platform engineer" from earlier turns.
- `ctx.get_history()` returns all user/assistant messages in order.
- Each call to `agent.run()` with `multi_turn=True` appends both the user message and assistant response to `ctx._history`.

### No-Backend Version (Simulated Memory)

```python
"""chatbot_memory_no_backend.py - Multi-turn chat without an LLM backend."""
import asyncio
from acp_agent_framework import ToolAgent, Context


async def memory_chat(ctx, tools):
    """Simple echo bot that remembers previous inputs."""
    user_input = ctx.get_input() or ""
    history = ctx.get_history()

    if not history:
        return f"Hello! You said: '{user_input}'. I will remember this."

    # Reference previous messages
    previous_topics = [msg["content"] for msg in history if msg["role"] == "user"]
    return (
        f"You said: '{user_input}'. "
        f"Previously, you mentioned: {', '.join(previous_topics)}."
    )


agent = ToolAgent(name="memory-bot", execute=memory_chat)


async def main():
    ctx = Context(session_id="mem-1", cwd=".")

    messages = ["I like Python", "Kubernetes is great", "What did I say before?"]
    for msg in messages:
        ctx.set_input(msg)
        # Manually add to history since ToolAgent does not do multi_turn automatically
        ctx.add_message("user", msg)

        async for event in agent.run(ctx):
            print(f"Bot: {event.content}")
            ctx.add_message("assistant", event.content)
        print()


asyncio.run(main())
```

---

## 6. Agent Orchestration (Agents Calling Agents)

`AgentTool` wraps any `BaseAgent` as a tool, enabling one agent to delegate work to another. This creates a hierarchical agent system where an orchestrator dispatches subtasks.

```python
"""agent_orchestration.py - Orchestrator delegating to specialist agents."""
import asyncio
from acp_agent_framework import ToolAgent, AgentTool, Context


# -- Specialist agents --

async def summarize(ctx, tools):
    """Summarize the given text."""
    text = ctx.get_input() or ""
    words = text.split()
    if len(words) > 20:
        summary = " ".join(words[:20]) + "..."
    else:
        summary = text
    return f"Summary: {summary}"


async def translate(ctx, tools):
    """Translate text to Spanish (simulated)."""
    text = ctx.get_input() or ""
    # Simulated translation
    translations = {
        "hello": "hola",
        "world": "mundo",
        "how are you": "como estas",
    }
    text_lower = text.lower()
    for eng, esp in translations.items():
        text_lower = text_lower.replace(eng, esp)
    return f"Translation: {text_lower}"


async def analyze_sentiment(ctx, tools):
    """Analyze sentiment of text (simulated)."""
    text = ctx.get_input() or ""
    positive_words = {"good", "great", "excellent", "happy", "love", "wonderful"}
    negative_words = {"bad", "terrible", "awful", "hate", "sad", "horrible"}
    words = set(text.lower().split())
    pos = len(words & positive_words)
    neg = len(words & negative_words)
    if pos > neg:
        sentiment = "POSITIVE"
    elif neg > pos:
        sentiment = "NEGATIVE"
    else:
        sentiment = "NEUTRAL"
    return f"Sentiment: {sentiment} (positive={pos}, negative={neg})"


summarizer = ToolAgent(
    name="summarizer",
    description="Summarizes text into a shorter form",
    execute=summarize,
)

translator = ToolAgent(
    name="translator",
    description="Translates text to Spanish",
    execute=translate,
)

sentiment_analyzer = ToolAgent(
    name="sentiment",
    description="Analyzes the sentiment of text",
    execute=analyze_sentiment,
)

# -- Wrap each specialist as an AgentTool --

summarizer_tool = AgentTool(summarizer)
translator_tool = AgentTool(translator)
sentiment_tool = AgentTool(sentiment_analyzer)


# -- Orchestrator that dispatches to specialists --

async def orchestrate(ctx, tools):
    """Parse commands and delegate to appropriate specialist agent."""
    user_input = ctx.get_input() or ""

    results = []

    if "summarize" in user_input.lower():
        # Extract the text after the command
        text = user_input.split(":", 1)[-1].strip() if ":" in user_input else user_input
        result = await tools["summarizer"].arun({"prompt": text})
        results.append(result)

    if "translate" in user_input.lower():
        text = user_input.split(":", 1)[-1].strip() if ":" in user_input else user_input
        result = await tools["translator"].arun({"prompt": text})
        results.append(result)

    if "sentiment" in user_input.lower():
        text = user_input.split(":", 1)[-1].strip() if ":" in user_input else user_input
        result = await tools["sentiment"].arun({"prompt": text})
        results.append(result)

    if not results:
        return "Unknown command. Use 'summarize:', 'translate:', or 'sentiment:'."

    return "\n".join(results)


orchestrator = ToolAgent(
    name="orchestrator",
    description="Orchestrates specialist agents",
    tools=[summarizer_tool, translator_tool, sentiment_tool],
    execute=orchestrate,
)


async def main():
    test_cases = [
        "summarize: The quick brown fox jumps over the lazy dog in a wonderful garden on a great sunny day",
        "translate: Hello World",
        "sentiment: This is a great and wonderful day",
        "summarize and sentiment: I love this excellent product it is wonderful and amazing",
    ]

    for user_input in test_cases:
        ctx = Context(session_id="orch-1", cwd=".")
        ctx.set_input(user_input)

        print(f"Input: {user_input}")
        async for event in orchestrator.run(ctx):
            for line in event.content.split("\n"):
                print(f"  -> {line}")
        print()


asyncio.run(main())
```

**Expected output:**

```
Input: summarize: The quick brown fox jumps over the lazy dog in a wonderful garden on a great sunny day
  -> Summary: The quick brown fox jumps over the lazy dog in a wonderful garden on a great sunny day

Input: translate: Hello World
  -> Translation: hola mundo

Input: sentiment: This is a great and wonderful day
  -> Sentiment: POSITIVE (positive=2, negative=0)

Input: summarize and sentiment: I love this excellent product it is wonderful and amazing
  -> Summary: I love this excellent product it is wonderful and amazing
  -> Sentiment: POSITIVE (positive=3, negative=0)
```

**How AgentTool works internally:**
1. `AgentTool.__init__` takes any `BaseAgent` and extracts its `name` and `description`.
2. When `arun({"prompt": "..."})` is called, it creates a fresh `Context`, sets the prompt as input, runs the wrapped agent, and collects all `message`-type events.
3. The collected messages are joined and returned as a string.

---

## 7. Secure Agent with Guardrails

`Guardrail` objects are validation functions applied before the prompt is sent (input guardrails) or after the response is received (output guardrails). A guardrail function takes a string and returns either a transformed string or `None` (meaning no changes). To reject content, raise `GuardrailError`.

```python
"""secure_agent.py - Agent with PII redaction and content filtering guardrails."""
import asyncio
import re
from acp_agent_framework import ToolAgent, Guardrail, GuardrailError, Context


# -- Input Guardrails --

def redact_emails(text: str) -> str:
    """Replace email addresses with [EMAIL REDACTED]."""
    return re.sub(
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "[EMAIL REDACTED]",
        text,
    )


def redact_phone_numbers(text: str) -> str:
    """Replace phone numbers with [PHONE REDACTED]."""
    # Matches common US formats: (123) 456-7890, 123-456-7890, 1234567890
    return re.sub(
        r"(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",
        "[PHONE REDACTED]",
        text,
    )


def redact_ssn(text: str) -> str:
    """Replace SSN patterns with [SSN REDACTED]."""
    return re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[SSN REDACTED]", text)


# -- Output Guardrails --

def block_sensitive_keywords(text: str) -> str:
    """Block responses containing sensitive keywords."""
    blocked_words = ["password", "secret_key", "api_key", "private_key", "credential"]
    text_lower = text.lower()
    for word in blocked_words:
        if word in text_lower:
            raise GuardrailError(
                f"Response blocked: contains sensitive keyword '{word}'",
                guardrail_name="block_sensitive_keywords",
            )
    return text  # Return unchanged if no blocked words found


def enforce_max_length(text: str) -> str:
    """Truncate response if it exceeds 500 characters."""
    if len(text) > 500:
        return text[:497] + "..."
    return text


# -- Build guardrails --

email_guardrail = Guardrail(name="redact-emails", fn=redact_emails)
phone_guardrail = Guardrail(name="redact-phones", fn=redact_phone_numbers)
ssn_guardrail = Guardrail(name="redact-ssn", fn=redact_ssn)
sensitive_guardrail = Guardrail(name="block-sensitive", fn=block_sensitive_keywords)
length_guardrail = Guardrail(name="max-length", fn=enforce_max_length)


# -- Agent that echoes input (to demonstrate guardrail transformations) --

async def echo_handler(ctx, tools):
    """Echo the (already-guardrailed) input back."""
    return f"Processed input: {ctx.get_input()}"


agent = ToolAgent(name="secure-agent", execute=echo_handler)


async def main():
    # Demonstrate input guardrails
    test_inputs = [
        "Contact me at john.doe@example.com or call 555-123-4567",
        "My SSN is 123-45-6789 and email is test@test.com",
        "No sensitive info here",
    ]

    print("=== Input Guardrail Demonstration ===\n")
    for raw_input in test_inputs:
        # Apply guardrails manually (as Agent.run() does internally)
        processed = raw_input
        for guardrail in [email_guardrail, phone_guardrail, ssn_guardrail]:
            processed = guardrail.validate(processed)

        print(f"  Raw:       {raw_input}")
        print(f"  Processed: {processed}")
        print()

    # Demonstrate output guardrails
    print("=== Output Guardrail Demonstration ===\n")
    test_outputs = [
        "Here is your data: all good.",
        "The password is hunter2 and the api_key is abc123.",
        "A" * 600,
    ]

    for raw_output in test_outputs:
        try:
            processed = raw_output
            for guardrail in [sensitive_guardrail, length_guardrail]:
                processed = guardrail.validate(processed)
            print(f"  Output ({len(raw_output)} chars): {processed[:80]}...")
        except GuardrailError as e:
            print(f"  BLOCKED: {e}")
        print()


asyncio.run(main())
```

**Expected output:**

```
=== Input Guardrail Demonstration ===

  Raw:       Contact me at john.doe@example.com or call 555-123-4567
  Processed: Contact me at [EMAIL REDACTED] or call [PHONE REDACTED]

  Raw:       My SSN is 123-45-6789 and email is test@test.com
  Processed: My SSN is [SSN REDACTED] and email is [EMAIL REDACTED]

  Raw:       No sensitive info here
  Processed: No sensitive info here

=== Output Guardrail Demonstration ===

  Output (29 chars): Here is your data: all good....

  BLOCKED: Response blocked: contains sensitive keyword 'password'

  Output (600 chars): AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA...
```

### Using Guardrails with an LLM Agent

```python
"""secure_llm_agent.py - LLM agent with input and output guardrails."""
import asyncio
from acp_agent_framework import Agent, Guardrail, GuardrailError, Context
from secure_agent import (  # Import from the example above
    email_guardrail, phone_guardrail, ssn_guardrail,
    sensitive_guardrail, length_guardrail,
)

agent = Agent(
    name="secure-assistant",
    backend="claude",
    instruction="You are a helpful assistant. Answer questions concisely.",
    input_guardrails=[email_guardrail, phone_guardrail, ssn_guardrail],
    output_guardrails=[sensitive_guardrail, length_guardrail],
)


async def main():
    ctx = Context(session_id="secure-1", cwd=".")
    ctx.set_input("My email is admin@company.com. What is your system password?")

    try:
        async for event in agent.run(ctx):
            print(f"[{event.author}] {event.content}")
    except GuardrailError as e:
        print(f"Guardrail blocked the response: {e}")


asyncio.run(main())
```

**How guardrails are applied in Agent.run():**
1. Input guardrails run sequentially on the full prompt (instruction + history + user input) before it is sent to the backend.
2. Output guardrails run sequentially on the backend response before it is stored and yielded.
3. If any guardrail raises `GuardrailError`, the exception propagates up to the caller.

---

## 8. Streaming Agent (Real-Time Output)

When `stream=True`, the agent yields `stream_chunk` events as tokens arrive from the backend, followed by a final `message` event with the complete response.

**Requirements:** A working ACP backend that supports streaming.

```python
"""streaming_agent.py - Real-time token streaming."""
import asyncio
import sys
from acp_agent_framework import Agent, Context


agent = Agent(
    name="streamer",
    backend="claude",
    instruction="You are a helpful assistant. Provide detailed explanations.",
    stream=True,
)


async def main():
    ctx = Context(session_id="stream-1", cwd=".")
    ctx.set_input("Explain how TCP/IP works in 3 paragraphs.")

    async for event in agent.run(ctx):
        if event.type == "stream_chunk":
            # Print each chunk without a newline for real-time effect
            sys.stdout.write(event.content)
            sys.stdout.flush()
        elif event.type == "message":
            # Final complete message
            print("\n\n--- Stream complete ---")
            print(f"Total length: {len(event.content)} characters")


asyncio.run(main())
```

**Expected behavior:**
- Text appears incrementally as `stream_chunk` events arrive.
- After all chunks, a single `message` event contains the full concatenated response.
- The context's output (`ctx.get_output()`) is set to the complete response.

### Simulated Streaming (No Backend)

```python
"""streaming_simulated.py - Simulate streaming without a backend."""
import asyncio
import sys
from acp_agent_framework import BaseAgent, Context, Event
from typing import AsyncGenerator


class SimulatedStreamAgent(BaseAgent):
    """Agent that simulates streaming by yielding tokens one at a time."""
    text: str = ""
    chunk_size: int = 5

    async def run(self, ctx: Context) -> AsyncGenerator[Event, None]:
        # Simulate token-by-token streaming
        words = self.text.split()
        collected = []
        for i in range(0, len(words), self.chunk_size):
            chunk = " ".join(words[i:i + self.chunk_size])
            if i > 0:
                chunk = " " + chunk
            collected.append(chunk)
            yield Event(author=self.name, type="stream_chunk", content=chunk)
            await asyncio.sleep(0.05)  # Simulate delay

        full_text = "".join(collected)
        ctx.set_output(full_text)
        yield Event(author=self.name, type="message", content=full_text)


async def main():
    agent = SimulatedStreamAgent(
        name="sim-stream",
        text=(
            "TCP/IP is the fundamental communication protocol suite of the internet. "
            "It defines how data is packaged, addressed, transmitted, routed, and "
            "received across networks. The protocol stack consists of four layers: "
            "the link layer, the internet layer, the transport layer, and the "
            "application layer."
        ),
        chunk_size=3,
    )

    ctx = Context(session_id="sim-1", cwd=".")

    async for event in agent.run(ctx):
        if event.type == "stream_chunk":
            sys.stdout.write(event.content)
            sys.stdout.flush()
        elif event.type == "message":
            print("\n\n--- Complete ---")


asyncio.run(main())
```

---

## 9. Google Chat Agent (Using Skills)

Skills are reusable instruction modules loaded from `SKILL.md` files following the [agentskills.io](https://agentskills.io) spec. They are discovered from:

1. Project-level: `.agents/skills/<skill-name>/SKILL.md`
2. User-level: `~/.agents/skills/<skill-name>/SKILL.md`

### Setting Up a Skill

First, create the skill definition:

```bash
mkdir -p .agents/skills/google-chat
```

Create `.agents/skills/google-chat/SKILL.md`:

```markdown
---
name: google-chat
description: Send messages via Google Chat
version: 1.0.0
dependencies: []
---

# Google Chat Skill

You can send direct messages using Google Chat.

## Available Commands

### Send a Direct Message
To send a DM, run the following command:
```
python scripts/chat.py send-dm <recipient_email> <message>
```

### Send to a Space
To send a message to a Google Chat space:
```
python scripts/chat.py send-space <space_id> <message>
```

## Important Notes
- The scripts directory is at: ~/.agents/skills/google-chat/scripts/
- Authentication is handled via service account credentials.
- Messages are limited to 4096 characters.
```

### Using the Skill with an LLM Agent

```python
"""google_chat_agent.py - Agent with the google-chat skill."""
import asyncio
from acp_agent_framework import Agent, Context


agent = Agent(
    name="chat-agent",
    backend="claude",
    instruction=(
        "You are a Google Chat assistant. Use the google-chat skill to send "
        "messages when the user requests it. Run the commands from the skill's "
        "scripts directory."
    ),
    skills=["google-chat"],  # Loaded from .agents/skills/google-chat/SKILL.md
)


async def main():
    ctx = Context(session_id="chat-1", cwd=".")
    ctx.set_input("Send a direct message to alice@example.com saying 'Meeting at 3pm'")

    async for event in agent.run(ctx):
        print(f"[{event.author}] {event.content}")


asyncio.run(main())
```

**What happens internally:**
1. `Agent.resolve_instruction()` calls `SkillLoader.load("google-chat", ctx.cwd)`.
2. The loader searches `.agents/skills/google-chat/SKILL.md` in the project, then `~/.agents/skills/google-chat/SKILL.md` at the user level.
3. The skill's instruction body is prepended to the agent's instruction.
4. Dependencies listed in the skill's YAML frontmatter are resolved in topological order.

### Using the Skill with ToolAgent (No Backend)

```python
"""google_chat_direct.py - Direct skill execution without LLM."""
import asyncio
import subprocess
from pathlib import Path
from acp_agent_framework import ToolAgent, Context


async def send_chat(ctx, tools):
    """Execute the google-chat skill script directly."""
    user_input = ctx.get_input() or ""

    # Parse the intent (simplified)
    skill_dir = Path.home() / ".agents" / "skills" / "google-chat"
    script_path = skill_dir / "scripts" / "chat.py"

    if not script_path.exists():
        return f"Skill script not found at {script_path}"

    # Example: extract email and message from input
    result = subprocess.run(
        ["python", str(script_path), "send-dm", "alice@example.com", "Meeting at 3pm"],
        cwd=str(skill_dir),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return f"Error: {result.stderr}"
    return result.stdout


agent = ToolAgent(
    name="chat-agent-direct",
    execute=send_chat,
)


async def main():
    ctx = Context(session_id="chat-direct-1", cwd=".")
    ctx.set_input("Send a DM to alice@example.com saying 'Meeting at 3pm'")

    async for event in agent.run(ctx):
        print(f"[{event.author}] {event.content}")


asyncio.run(main())
```

### Discovering Available Skills

```python
"""discover_skills.py - List all available skills."""
from acp_agent_framework import SkillLoader

skills = SkillLoader.discover(cwd=".")
for skill_name, skill in skills.items():
    print(f"Skill: {skill.name}")
    print(f"  Description: {skill.description}")
    print(f"  Path: {skill.path}")
    print(f"  Dependencies: {[d.name for d in skill.dependencies]}")
    print()
```

---

## 10. Full Production Setup (HTTP Server with Logging)

A production-ready agent served over HTTP with structured JSON logging, guardrails, skills, and tools. The HTTP server provides a REST API with SSE streaming.

```python
"""production_setup.py - Full production agent with observability."""
import asyncio
import re
import time
from acp_agent_framework import (
    Agent,
    Context,
    FunctionTool,
    Guardrail,
    GuardrailError,
    AgentLogger,
    get_logger,
    serve,
)

# -- Logging --

logger = get_logger("production")


# -- Tools --

def lookup_user(user_id: str) -> str:
    """Look up a user by ID in the database."""
    logger.tool_call("lookup_user", {"user_id": user_id})
    # Simulated database lookup
    users = {
        "u001": "Alice Johnson (Engineering)",
        "u002": "Bob Smith (Marketing)",
        "u003": "Carol White (Finance)",
    }
    result = users.get(user_id, f"User {user_id} not found")
    logger.tool_result("lookup_user", result)
    return result


def create_ticket(title: str, priority: str) -> str:
    """Create a support ticket."""
    logger.tool_call("create_ticket", {"title": title, "priority": priority})
    ticket_id = f"TICKET-{int(time.time()) % 10000}"
    result = f"Created {ticket_id}: '{title}' (priority: {priority})"
    logger.tool_result("create_ticket", result)
    return result


user_tool = FunctionTool(lookup_user)
ticket_tool = FunctionTool(create_ticket)


# -- Guardrails --

def redact_pii(text: str) -> str:
    """Redact common PII patterns."""
    text = re.sub(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "[EMAIL]", text)
    text = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[SSN]", text)
    return text


def block_prompt_injection(text: str) -> str:
    """Block common prompt injection patterns."""
    injection_patterns = [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"you\s+are\s+now\s+DAN",
        r"disregard\s+your\s+(system\s+)?prompt",
    ]
    for pattern in injection_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            raise GuardrailError(
                "Potential prompt injection detected",
                guardrail_name="block_prompt_injection",
            )
    return text


pii_guardrail = Guardrail(name="redact-pii", fn=redact_pii)
injection_guardrail = Guardrail(name="block-injection", fn=block_prompt_injection)
output_pii_guardrail = Guardrail(name="output-redact-pii", fn=redact_pii)


# -- Agent with lifecycle hooks --

async def on_start(ctx: Context):
    """Called before the agent runs."""
    logger.agent_start("production-agent", ctx.session_id)


async def on_end(ctx: Context):
    """Called after the agent runs."""
    logger.agent_end("production-agent", ctx.session_id, duration_ms=0)


# -- Build the agent --

agent = Agent(
    name="production-agent",
    backend="claude",
    instruction=(
        "You are a production support assistant for an enterprise application. "
        "You can look up users and create support tickets. Be professional "
        "and concise. Always confirm actions before executing them."
    ),
    tools=[user_tool, ticket_tool],
    input_guardrails=[injection_guardrail, pii_guardrail],
    output_guardrails=[output_pii_guardrail],
    before_run=on_start,
    after_run=on_end,
)

if __name__ == "__main__":
    # Option 1: Serve via HTTP (REST API with SSE streaming)
    # Access the web UI at http://localhost:8000
    # API endpoints:
    #   POST /api/sessions          - Create a session
    #   GET  /api/sessions/{id}     - Get session info
    #   POST /api/sessions/{id}/prompt - Send a prompt (returns SSE stream)
    #   DELETE /api/sessions/{id}   - Delete a session
    serve(agent, transport="http", host="0.0.0.0", port=8000)

    # Option 2: Serve via ACP (stdio protocol)
    # serve(agent, transport="acp")
```

**HTTP API usage with curl:**

```bash
# Create a session
curl -X POST http://localhost:8000/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"cwd": "."}'
# Returns: {"session_id": "abc-123", "cwd": "."}

# Send a prompt (SSE stream)
curl -N http://localhost:8000/api/sessions/abc-123/prompt \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"text": "Look up user u001"}'
# Returns SSE events:
# data: {"id": "...", "author": "production-agent", "type": "message", "content": "..."}
# data: [DONE]

# Delete session
curl -X DELETE http://localhost:8000/api/sessions/abc-123
```

**Structured log output (JSON, one line per entry):**

```json
{"timestamp": 1709654321.123, "level": "INFO", "agent_name": "production-agent", "session_id": "abc-123", "message": "Agent started: production-agent"}
{"timestamp": 1709654321.456, "level": "DEBUG", "agent_name": null, "session_id": null, "message": "Tool call: lookup_user", "tool_name": "lookup_user", "tool_args": {"user_id": "u001"}}
{"timestamp": 1709654321.789, "level": "INFO", "agent_name": "production-agent", "session_id": "abc-123", "message": "Agent finished: production-agent (1234.5ms)", "duration_ms": 1234.5}
```

Set the log level via environment variable:

```bash
AGENT_LOG_LEVEL=DEBUG python production_setup.py
```

---

## 11. Custom Agent Type (Subclassing BaseAgent)

Create custom agent types by subclassing `BaseAgent`. You must implement the `run()` async generator method. Custom agents can implement any logic: rule engines, state machines, external API calls, or entirely custom LLM interactions.

### Example: Retry Agent

An agent that retries a sub-agent up to N times on failure:

```python
"""custom_retry_agent.py - Agent that retries on failure."""
import asyncio
from typing import AsyncGenerator, Optional
from pydantic import Field
from acp_agent_framework import BaseAgent, Context, Event


class RetryAgent(BaseAgent):
    """Wraps another agent and retries on error up to max_retries times."""

    agent: BaseAgent
    max_retries: int = 3
    retry_delay: float = 1.0

    async def run(self, ctx: Context) -> AsyncGenerator[Event, None]:
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                events = []
                async for event in self.agent.run(ctx):
                    events.append(event)

                # If we got here, the agent succeeded
                yield Event(
                    author=self.name,
                    type="info",
                    content=f"Succeeded on attempt {attempt}/{self.max_retries}",
                )
                for event in events:
                    yield event
                return

            except Exception as e:
                last_error = e
                yield Event(
                    author=self.name,
                    type="warning",
                    content=f"Attempt {attempt}/{self.max_retries} failed: {e}",
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay)

        yield Event(
            author=self.name,
            type="error",
            content=f"All {self.max_retries} attempts failed. Last error: {last_error}",
        )


# -- Test with a flaky agent --

class FlakyAgent(BaseAgent):
    """Agent that fails the first N times, then succeeds."""
    fail_count: int = 2
    _attempts: int = 0

    class Config:
        # Allow mutable private attributes
        underscore_attrs_are_private = True

    async def run(self, ctx: Context) -> AsyncGenerator[Event, None]:
        self._attempts += 1
        if self._attempts <= self.fail_count:
            raise ConnectionError(f"Simulated failure #{self._attempts}")
        yield Event(
            author=self.name,
            type="message",
            content=f"Success after {self._attempts} attempts!",
        )


async def main():
    flaky = FlakyAgent(name="flaky", fail_count=2)
    retry = RetryAgent(
        name="retry-wrapper",
        agent=flaky,
        max_retries=5,
        retry_delay=0.1,
    )

    ctx = Context(session_id="retry-1", cwd=".")

    async for event in retry.run(ctx):
        print(f"[{event.type}] {event.content}")


asyncio.run(main())
```

**Expected output:**

```
[warning] Attempt 1/5 failed: Simulated failure #1
[warning] Attempt 2/5 failed: Simulated failure #2
[info] Succeeded on attempt 3/5
[message] Success after 3 attempts!
```

### Example: Conditional Branch Agent

```python
"""custom_branch_agent.py - Agent that branches based on state."""
import asyncio
from typing import AsyncGenerator, Dict
from pydantic import Field
from acp_agent_framework import BaseAgent, ToolAgent, Context, Event


class BranchAgent(BaseAgent):
    """Routes to different agents based on a state key's value."""

    state_key: str
    branches: Dict[str, BaseAgent] = Field(default_factory=dict)
    fallback: BaseAgent | None = None

    async def run(self, ctx: Context) -> AsyncGenerator[Event, None]:
        value = str(ctx.state.get(self.state_key, "")).lower()

        yield Event(
            author=self.name,
            type="info",
            content=f"Branching on '{self.state_key}' = '{value}'",
        )

        target = self.branches.get(value, self.fallback)
        if target is None:
            yield Event(
                author=self.name,
                type="error",
                content=f"No branch for value '{value}' and no fallback defined.",
            )
            return

        async for event in target.run(ctx):
            yield event


# -- Usage --

async def handle_new(ctx, tools):
    return "Processing new customer onboarding."


async def handle_existing(ctx, tools):
    return "Loading existing customer profile."


async def handle_vip(ctx, tools):
    return "Routing to VIP support team."


async def handle_unknown(ctx, tools):
    return "Unknown customer type. Please classify first."


branch = BranchAgent(
    name="customer-router",
    state_key="customer_type",
    branches={
        "new": ToolAgent(name="new-handler", execute=handle_new),
        "existing": ToolAgent(name="existing-handler", execute=handle_existing),
        "vip": ToolAgent(name="vip-handler", execute=handle_vip),
    },
    fallback=ToolAgent(name="unknown-handler", execute=handle_unknown),
)


async def main():
    for customer_type in ["new", "existing", "vip", "enterprise"]:
        ctx = Context(session_id="branch-1", cwd=".")
        ctx.state.set("customer_type", customer_type)

        print(f"Customer type: {customer_type}")
        async for event in branch.run(ctx):
            print(f"  [{event.type}] {event.content}")
        print()


asyncio.run(main())
```

**Expected output:**

```
Customer type: new
  [info] Branching on 'customer_type' = 'new'
  [tool_result] Processing new customer onboarding.

Customer type: existing
  [info] Branching on 'customer_type' = 'existing'
  [tool_result] Loading existing customer profile.

Customer type: vip
  [info] Branching on 'customer_type' = 'vip'
  [tool_result] Routing to VIP support team.

Customer type: enterprise
  [info] Branching on 'customer_type' = 'enterprise'
  [tool_result] Unknown customer type. Please classify first.
```

### Example: Map-Reduce Agent

```python
"""custom_mapreduce_agent.py - Process items in parallel, then reduce."""
import asyncio
from typing import Any, AsyncGenerator, Callable
from pydantic import Field
from acp_agent_framework import BaseAgent, Context, Event, State


class MapReduceAgent(BaseAgent):
    """Apply a sub-agent to each item in a list, then reduce results."""

    items_key: str  # State key containing list of items
    worker: BaseAgent
    reduce_fn: Callable[[list[str]], str] = Field(exclude=True)

    async def run(self, ctx: Context) -> AsyncGenerator[Event, None]:
        items = ctx.state.get(self.items_key, [])
        if not items:
            yield Event(author=self.name, type="error", content="No items to process.")
            return

        yield Event(
            author=self.name,
            type="info",
            content=f"Processing {len(items)} items.",
        )

        # Map phase: run worker on each item
        results = []
        for i, item in enumerate(items):
            worker_ctx = Context(session_id=f"{ctx.session_id}-map-{i}", cwd=ctx.cwd)
            worker_ctx.set_input(str(item))

            async for event in self.worker.run(worker_ctx):
                if event.type in ("message", "tool_result"):
                    results.append(event.content)

            yield Event(
                author=self.name,
                type="progress",
                content=f"Processed item {i + 1}/{len(items)}: {item}",
            )

        # Reduce phase
        final = self.reduce_fn(results)
        ctx.set_output(final)
        yield Event(author=self.name, type="message", content=final)


# -- Usage --

from acp_agent_framework import ToolAgent


async def word_count(ctx, tools):
    text = ctx.get_input() or ""
    count = len(text.split())
    return str(count)


def sum_reduce(results: list[str]) -> str:
    total = sum(int(r) for r in results if r.isdigit())
    return f"Total word count across all documents: {total}"


worker = ToolAgent(name="word-counter", execute=word_count)

map_reduce = MapReduceAgent(
    name="word-count-pipeline",
    items_key="documents",
    worker=worker,
    reduce_fn=sum_reduce,
)


async def main():
    ctx = Context(session_id="mr-1", cwd=".")
    ctx.state.set("documents", [
        "The quick brown fox jumps over the lazy dog",
        "Hello world this is a test document with some words",
        "Short doc",
    ])

    async for event in map_reduce.run(ctx):
        print(f"[{event.type}] {event.content}")


asyncio.run(main())
```

**Expected output:**

```
[info] Processing 3 items.
[progress] Processed item 1/3: The quick brown fox jumps over the lazy dog
[progress] Processed item 2/3: Hello world this is a test document with some words
[progress] Processed item 3/3: Short doc
[message] Total word count across all documents: 21
```

---

## 12. Testing Agents (Unit Tests)

Testing agents effectively requires mocking the ACP backend (for `Agent`) or providing predictable execute functions (for `ToolAgent`). Below are patterns for each scenario.

### 12a. Testing ToolAgent (No Mocking Needed)

`ToolAgent` does not call any external services, making it trivially testable:

```python
"""test_tool_agent.py - Unit tests for ToolAgent."""
import asyncio
import pytest
from acp_agent_framework import ToolAgent, Context, FunctionTool


# -- Agent under test --

def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


async def calculator_execute(ctx, tools):
    user_input = ctx.get_input() or ""
    parts = user_input.split("+")
    if len(parts) == 2:
        a, b = int(parts[0].strip()), int(parts[1].strip())
        result = tools["add"].run({"a": a, "b": b})
        return str(result)
    return "Please provide input in format: X + Y"


add_tool = FunctionTool(add)
agent = ToolAgent(name="calc", tools=[add_tool], execute=calculator_execute)


# -- Tests --

@pytest.mark.asyncio
async def test_basic_addition():
    ctx = Context(session_id="test-1", cwd=".")
    ctx.set_input("3 + 5")

    events = []
    async for event in agent.run(ctx):
        events.append(event)

    assert len(events) == 1
    assert events[0].type == "tool_result"
    assert events[0].content == "8"
    assert events[0].author == "calc"
    assert ctx.get_output() == "8"


@pytest.mark.asyncio
async def test_invalid_input():
    ctx = Context(session_id="test-2", cwd=".")
    ctx.set_input("hello")

    events = []
    async for event in agent.run(ctx):
        events.append(event)

    assert "format" in events[0].content.lower()


@pytest.mark.asyncio
async def test_output_key():
    agent_with_key = ToolAgent(
        name="calc",
        tools=[add_tool],
        execute=calculator_execute,
        output_key="result",
    )
    ctx = Context(session_id="test-3", cwd=".")
    ctx.set_input("10 + 20")

    async for _ in agent_with_key.run(ctx):
        pass

    assert ctx.state.get("result") == "30"


@pytest.mark.asyncio
async def test_before_after_hooks():
    hooks_called = []

    async def before(ctx):
        hooks_called.append("before")

    async def after(ctx):
        hooks_called.append("after")

    hooked_agent = ToolAgent(
        name="hooked",
        tools=[],
        execute=calculator_execute,
        before_run=before,
        after_run=after,
    )
    ctx = Context(session_id="test-4", cwd=".")
    ctx.set_input("1 + 2")

    async for _ in hooked_agent.run(ctx):
        pass

    assert hooks_called == ["before", "after"]
```

Run with:

```bash
pytest test_tool_agent.py -v
```

### 12b. Testing Agent with Mocked Backend

To test `Agent` without a live backend, mock the `AcpBackend` class:

```python
"""test_agent_mocked.py - Unit tests for Agent with mocked backend."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from acp_agent_framework import Agent, Context, Guardrail, GuardrailError


# -- Mock the backend --

def create_mock_backend(response_text="Mocked response"):
    """Create a mocked AcpBackend that returns a fixed response."""
    mock = MagicMock()
    mock.start = AsyncMock()
    mock.stop = AsyncMock()
    mock.new_session = AsyncMock(return_value="mock-session-id")
    mock.prompt = AsyncMock(return_value=response_text)
    return mock


@pytest.mark.asyncio
async def test_agent_basic_flow():
    agent = Agent(
        name="test-agent",
        backend="claude",
        instruction="You are a test assistant.",
    )

    mock_backend = create_mock_backend("Hello from mock!")

    with patch.object(agent, "_get_backend", return_value=mock_backend):
        ctx = Context(session_id="test-1", cwd=".")
        ctx.set_input("Say hello")

        events = []
        async for event in agent.run(ctx):
            events.append(event)

    # Verify the agent produced the expected event
    assert len(events) == 1
    assert events[0].type == "message"
    assert events[0].content == "Hello from mock!"
    assert events[0].author == "test-agent"

    # Verify context was updated
    assert ctx.get_output() == "Hello from mock!"

    # Verify backend lifecycle
    mock_backend.start.assert_awaited_once()
    mock_backend.stop.assert_awaited_once()
    mock_backend.new_session.assert_awaited_once()


@pytest.mark.asyncio
async def test_agent_with_output_key():
    agent = Agent(
        name="test-agent",
        backend="claude",
        instruction="Test",
        output_key="my_result",
    )

    mock_backend = create_mock_backend("Stored result")

    with patch.object(agent, "_get_backend", return_value=mock_backend):
        ctx = Context(session_id="test-2", cwd=".")
        ctx.set_input("Go")

        async for _ in agent.run(ctx):
            pass

    assert ctx.state.get("my_result") == "Stored result"


@pytest.mark.asyncio
async def test_agent_callable_instruction():
    agent = Agent(
        name="test-agent",
        backend="claude",
        instruction=lambda ctx: f"Process: {ctx.state.get('mode', 'default')}",
    )

    mock_backend = create_mock_backend("OK")

    with patch.object(agent, "_get_backend", return_value=mock_backend):
        ctx = Context(session_id="test-3", cwd=".")
        ctx.state.set("mode", "analysis")
        ctx.set_input("Run")

        async for _ in agent.run(ctx):
            pass

    # Verify the prompt included the resolved instruction
    call_args = mock_backend.prompt.call_args
    prompt = call_args[0][1]  # Second positional arg is the prompt text
    assert "Process: analysis" in prompt


@pytest.mark.asyncio
async def test_agent_input_guardrail_transforms():
    def censor(text):
        return text.replace("bad", "***")

    agent = Agent(
        name="test-agent",
        backend="claude",
        instruction="Test",
        input_guardrails=[Guardrail(name="censor", fn=censor)],
    )

    mock_backend = create_mock_backend("OK")

    with patch.object(agent, "_get_backend", return_value=mock_backend):
        ctx = Context(session_id="test-4", cwd=".")
        ctx.set_input("This has bad words")

        async for _ in agent.run(ctx):
            pass

    prompt = mock_backend.prompt.call_args[0][1]
    assert "bad" not in prompt
    assert "***" in prompt


@pytest.mark.asyncio
async def test_agent_output_guardrail_blocks():
    def block_secrets(text):
        if "secret" in text.lower():
            raise GuardrailError("Blocked: contains secret", "block_secrets")
        return text

    agent = Agent(
        name="test-agent",
        backend="claude",
        instruction="Test",
        output_guardrails=[Guardrail(name="block-secrets", fn=block_secrets)],
    )

    mock_backend = create_mock_backend("The secret code is 1234")

    with patch.object(agent, "_get_backend", return_value=mock_backend):
        ctx = Context(session_id="test-5", cwd=".")
        ctx.set_input("Tell me a secret")

        with pytest.raises(GuardrailError, match="Blocked: contains secret"):
            async for _ in agent.run(ctx):
                pass


@pytest.mark.asyncio
async def test_agent_multi_turn():
    agent = Agent(
        name="test-agent",
        backend="claude",
        instruction="Test",
        multi_turn=True,
    )

    mock_backend = create_mock_backend("Reply 1")

    with patch.object(agent, "_get_backend", return_value=mock_backend):
        ctx = Context(session_id="test-6", cwd=".")

        # Turn 1
        ctx.set_input("Hello")
        async for _ in agent.run(ctx):
            pass

        assert len(ctx.get_history()) == 2  # user + assistant
        assert ctx.get_history()[0] == {"role": "user", "content": "Hello"}
        assert ctx.get_history()[1] == {"role": "assistant", "content": "Reply 1"}


@pytest.mark.asyncio
async def test_agent_streaming():
    agent = Agent(
        name="test-agent",
        backend="claude",
        instruction="Test",
        stream=True,
    )

    mock_backend = create_mock_backend()

    async def mock_stream(session_id, text):
        for chunk in ["Hello", " ", "world", "!"]:
            yield chunk

    mock_backend.prompt_stream = mock_stream

    with patch.object(agent, "_get_backend", return_value=mock_backend):
        ctx = Context(session_id="test-7", cwd=".")
        ctx.set_input("Stream test")

        events = []
        async for event in agent.run(ctx):
            events.append(event)

    # Should have 4 stream chunks + 1 final message
    chunk_events = [e for e in events if e.type == "stream_chunk"]
    message_events = [e for e in events if e.type == "message"]

    assert len(chunk_events) == 4
    assert chunk_events[0].content == "Hello"
    assert len(message_events) == 1
    assert message_events[0].content == "Hello world!"
```

### 12c. Testing Sequential and Router Agents

```python
"""test_pipelines.py - Test sequential and router agent compositions."""
import asyncio
import pytest
from acp_agent_framework import (
    ToolAgent, SequentialAgent, RouterAgent, Route, Context,
)


# -- Helpers --

async def upper(ctx, tools):
    return (ctx.get_input() or "").upper()


async def reverse(ctx, tools):
    return (ctx.get_input() or "")[::-1]


async def exclaim(ctx, tools):
    text = ctx.state.get("step1", ctx.get_input() or "")
    return f"{text}!!!"


# -- Sequential Tests --

@pytest.mark.asyncio
async def test_sequential_runs_in_order():
    step1 = ToolAgent(name="step1", execute=upper, output_key="step1")
    step2 = ToolAgent(name="step2", execute=exclaim)

    pipeline = SequentialAgent(name="pipeline", agents=[step1, step2])

    ctx = Context(session_id="seq-1", cwd=".")
    ctx.set_input("hello")

    events = []
    async for event in pipeline.run(ctx):
        events.append(event)

    assert len(events) == 2
    assert events[0].content == "HELLO"      # step1: uppercase
    assert events[1].content == "HELLO!!!"    # step2: reads from state


@pytest.mark.asyncio
async def test_sequential_stores_agent_outputs():
    step1 = ToolAgent(name="step1", execute=upper, output_key="upper_result")
    step2 = ToolAgent(name="step2", execute=reverse, output_key="reversed_result")

    pipeline = SequentialAgent(name="pipeline", agents=[step1, step2])

    ctx = Context(session_id="seq-2", cwd=".")
    ctx.set_input("hello")

    async for _ in pipeline.run(ctx):
        pass

    # Agent outputs are stored on context
    assert ctx.get_agent_output("step1") == "HELLO"
    assert ctx.get_agent_output("step2") == "OLLEH"

    # State keys are also set
    assert ctx.state.get("upper_result") == "HELLO"
    assert ctx.state.get("reversed_result") == "OLLEH"


# -- Router Tests --

@pytest.mark.asyncio
async def test_router_matches_keyword():
    code_agent = ToolAgent(name="code", execute=upper)
    writing_agent = ToolAgent(name="writing", execute=reverse)

    router = RouterAgent(
        name="router",
        routes=[
            Route(keywords=["code", "python"], agent=code_agent),
            Route(keywords=["write", "essay"], agent=writing_agent),
        ],
    )

    ctx = Context(session_id="route-1", cwd=".")
    ctx.set_input("Help me with python code")

    events = []
    async for event in router.run(ctx):
        events.append(event)

    assert events[0].author == "code"


@pytest.mark.asyncio
async def test_router_uses_default():
    default = ToolAgent(name="default", execute=upper)

    router = RouterAgent(
        name="router",
        routes=[Route(keywords=["code"], agent=ToolAgent(name="code", execute=reverse))],
        default_agent=default,
    )

    ctx = Context(session_id="route-2", cwd=".")
    ctx.set_input("What is the weather?")

    events = []
    async for event in router.run(ctx):
        events.append(event)

    assert events[0].author == "default"
    assert events[0].content == "WHAT IS THE WEATHER?"


@pytest.mark.asyncio
async def test_router_no_match_no_default():
    router = RouterAgent(
        name="router",
        routes=[Route(keywords=["code"], agent=ToolAgent(name="code", execute=upper))],
        default_agent=None,
    )

    ctx = Context(session_id="route-3", cwd=".")
    ctx.set_input("random question")

    events = []
    async for event in router.run(ctx):
        events.append(event)

    assert len(events) == 1
    assert "No matching route" in events[0].content
```

### 12d. Testing Events and State

```python
"""test_events_state.py - Test Event and State objects directly."""
import pytest
from acp_agent_framework import Event, EventActions, State, Context


# -- Event Tests --

def test_event_has_auto_id():
    event = Event(author="test", type="message", content="hello")
    assert event.id is not None
    assert len(event.id) > 0


def test_event_has_timestamp():
    event = Event(author="test", type="message", content="hello")
    assert event.timestamp > 0


def test_event_with_actions():
    actions = EventActions(
        state_delta={"key": "value"},
        transfer_to_agent="other-agent",
        escalate=True,
    )
    event = Event(author="test", type="message", content="hello", actions=actions)
    assert event.actions.state_delta == {"key": "value"}
    assert event.actions.transfer_to_agent == "other-agent"
    assert event.actions.escalate is True


# -- State Tests --

def test_state_get_set():
    state = State()
    state.set("name", "Alice")
    assert state.get("name") == "Alice"


def test_state_default_value():
    state = State()
    assert state.get("missing", "fallback") == "fallback"


def test_state_initial_data():
    state = State(initial={"a": 1, "b": 2})
    assert state.get("a") == 1
    assert state.get("b") == 2


def test_state_delta_tracking():
    state = State(initial={"a": 1})
    state.set("b", 2)
    state.set("c", 3)

    delta = state.get_delta()
    assert delta == {"b": 2, "c": 3}
    assert "a" not in delta  # Initial data is not in delta


def test_state_commit_clears_delta():
    state = State()
    state.set("x", 10)
    assert state.get_delta() == {"x": 10}

    state.commit()
    assert state.get_delta() == {}
    assert state.get("x") == 10  # Data still accessible


def test_state_persistable_excludes_temp():
    state = State()
    state.set("important", "keep")
    state.set("temp:cache", "discard")

    persistable = state.get_persistable()
    assert "important" in persistable
    assert "temp:cache" not in persistable


def test_state_to_dict():
    state = State(initial={"a": 1})
    state.set("b", 2)
    assert state.to_dict() == {"a": 1, "b": 2}


# -- Context Tests --

def test_context_input_output():
    ctx = Context(session_id="t1", cwd="/tmp")
    assert ctx.get_input() is None
    assert ctx.get_output() is None

    ctx.set_input("hello")
    ctx.set_output("world")

    assert ctx.get_input() == "hello"
    assert ctx.get_output() == "world"


def test_context_agent_outputs():
    ctx = Context(session_id="t2", cwd=".")
    ctx.set_agent_output("agent1", "result1")
    ctx.set_agent_output("agent2", "result2")

    assert ctx.get_agent_output("agent1") == "result1"
    assert ctx.get_agent_output("agent2") == "result2"
    assert ctx.get_agent_output("agent3") is None


def test_context_history():
    ctx = Context(session_id="t3", cwd=".")
    ctx.add_message("user", "hello")
    ctx.add_message("assistant", "hi there")

    history = ctx.get_history()
    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "hello"}
    assert history[1] == {"role": "assistant", "content": "hi there"}

    ctx.clear_history()
    assert len(ctx.get_history()) == 0
```

### 12e. Testing with Session Persistence

```python
"""test_persistence.py - Test JsonSessionStore."""
import pytest
import tempfile
from pathlib import Path
from acp_agent_framework.persistence import JsonSessionStore


@pytest.fixture
def store(tmp_path):
    return JsonSessionStore(tmp_path)


def test_save_and_load(store):
    store.save("session-1", {"user": "alice", "turn": 1})
    data = store.load("session-1")
    assert data == {"user": "alice", "turn": 1}


def test_load_nonexistent(store):
    assert store.load("does-not-exist") is None


def test_delete(store):
    store.save("session-2", {"data": "test"})
    assert store.load("session-2") is not None

    store.delete("session-2")
    assert store.load("session-2") is None


def test_list_sessions(store):
    store.save("s1", {})
    store.save("s2", {})
    store.save("s3", {})

    sessions = store.list_sessions()
    assert set(sessions) == {"s1", "s2", "s3"}


def test_overwrite(store):
    store.save("s1", {"version": 1})
    store.save("s1", {"version": 2})
    assert store.load("s1") == {"version": 2}
```

Run all tests:

```bash
pytest test_tool_agent.py test_agent_mocked.py test_pipelines.py test_events_state.py test_persistence.py -v
```

---

## Appendix A: Backend Registration

Register custom backends before creating agents:

```python
"""custom_backend.py - Register a custom ACP backend."""
from acp_agent_framework import BackendRegistry, BackendConfig, Agent

registry = BackendRegistry()

# Register a local Ollama backend
registry.register(
    "local-llama",
    BackendConfig(
        command="ollama-acp",
        args=["--model", "llama3"],
        env={"OLLAMA_HOST": "http://localhost:11434"},
        timeout=60.0,
        max_retries=2,
        retry_base_delay=0.5,
    ),
)

# Now use it
agent = Agent(
    name="local-agent",
    backend="local-llama",
    instruction="You are a helpful assistant running locally.",
)

# List all available backends
print("Available backends:", registry.list())
# Output: Available backends: ['claude', 'gemini', 'codex', 'openai', 'ollama', 'local-llama']
```

`BackendRegistry` is a singleton -- registrations persist across all modules in the process.

---

## Appendix B: Session Persistence

Save and restore agent state across sessions:

```python
"""session_persistence.py - Save and restore session state."""
import asyncio
from pathlib import Path
from acp_agent_framework import ToolAgent, Context, State
from acp_agent_framework.persistence import JsonSessionStore

store = JsonSessionStore(Path("./sessions"))


async def counter(ctx, tools):
    count = ctx.state.get("count", 0) + 1
    ctx.state.set("count", count)
    return f"Count is now {count}"


agent = ToolAgent(name="counter", execute=counter)


async def run_with_persistence(session_id: str):
    # Restore previous state if it exists
    saved = store.load(session_id)
    state = State(initial=saved) if saved else State()
    ctx = Context(session_id=session_id, cwd=".", state=state)

    async for event in agent.run(ctx):
        print(event.content)

    # Save state for next time
    store.save(session_id, ctx.state.get_persistable())


async def main():
    # Run three times with the same session -- count increments
    for _ in range(3):
        await run_with_persistence("persistent-session-1")

    # Output:
    # Count is now 1
    # Count is now 2
    # Count is now 3


asyncio.run(main())
```

---

## Appendix C: Event Types Reference

| Event Type | Produced By | Description |
|---|---|---|
| `message` | `Agent` | Complete LLM response |
| `stream_chunk` | `Agent` (stream=True) | Individual token/chunk during streaming |
| `tool_result` | `ToolAgent` | Result from tool execution |
| `info` | Custom agents | Informational message |
| `warning` | Custom agents | Warning message |
| `error` | Custom agents | Error message |
| `progress` | Custom agents | Progress update |

Custom agent types may define additional event types as needed.

---

## Appendix D: Architecture Overview

```
Agent (LLM-backed)
  |-- Backend (AcpBackend via BackendRegistry)
  |-- Tools (FunctionTool -> McpBridge -> MCP server)
  |-- Skills (SkillLoader -> SKILL.md files)
  |-- Guardrails (input/output validation)
  |-- Context (session state, history, I/O)

SequentialAgent
  |-- agents: list[BaseAgent] (runs in order)

RouterAgent
  |-- routes: list[Route] (keyword matching)
  |-- default_agent: BaseAgent (fallback)

ToolAgent (no LLM)
  |-- tools: list[BaseTool]
  |-- execute: Callable (user-defined logic)

AgentTool
  |-- Wraps any BaseAgent as a BaseTool
  |-- Enables agent-to-agent delegation
```
