# Contributing to ACP Agent Framework

Thanks for your interest in contributing! This guide will help you get started.

## Development Setup

```bash
# Clone the repo
git clone https://github.com/sanjay3290/agentic-framework-acp.git
cd agentic-framework-acp

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[all]"
```

## Running Tests

```bash
# Unit tests
pytest tests/ -v

# Integration tests (requires backends installed)
pytest tests/ -v -m integration

# Lint
ruff check src/ tests/
```

## Project Structure

- `src/acp_agent_framework/` - Main package
  - `agents/` - Agent implementations (Agent, ToolAgent, SequentialAgent, RouterAgent)
  - `backends/` - ACP backend management (registry, subprocess lifecycle)
  - `server/` - ACP stdio server and HTTP/FastAPI server
  - `tools/` - Tool system (FunctionTool, MCP bridge)
  - `skills/` - Skill loader (agentskills.io spec)
- `tests/` - Test suite
- `examples/` - Example agents

## Making Changes

1. Fork the repo and create a feature branch from `main`
2. Make your changes
3. Add or update tests for your changes
4. Ensure all tests pass: `pytest tests/ -v`
5. Ensure lint is clean: `ruff check src/ tests/`
6. Submit a pull request

## Code Style

- Follow existing patterns in the codebase
- Use type hints for function signatures
- Keep modules focused and small
- Use `ruff` for linting (config in `pyproject.toml`)

## Adding a New Backend

1. Add entry to `DEFAULT_BACKENDS` in `src/acp_agent_framework/backends/registry.py`
2. Or register at runtime:

```python
from acp_agent_framework import BackendConfig, BackendRegistry

registry = BackendRegistry()
registry.register("my-backend", BackendConfig(
    command="my-agent-binary",
    args=["--acp"],
))
```

## Adding a New Agent Type

1. Subclass `BaseAgent` from `src/acp_agent_framework/agents/base.py`
2. Implement the `run(ctx)` async generator method
3. Export from `src/acp_agent_framework/__init__.py`
4. Add tests

## Adding Tools

Wrap any Python function as a tool:

```python
from acp_agent_framework import FunctionTool

def my_tool(query: str) -> str:
    """Tool description shown to the LLM."""
    return f"Result for {query}"

tool = FunctionTool(my_tool)
```

## Reporting Issues

Open an issue at https://github.com/sanjay3290/agentic-framework-acp/issues with:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Python version and OS

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
