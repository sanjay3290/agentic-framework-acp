import pytest
from acp_agent_framework.tools.function_tool import FunctionTool

def test_function_tool_from_sync():
    def greet(name: str) -> str:
        """Greet a person."""
        return f"Hello, {name}!"
    tool = FunctionTool(greet)
    assert tool.name == "greet"
    assert tool.description == "Greet a person."

def test_function_tool_sync_run():
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b
    tool = FunctionTool(add)
    result = tool.run(args={"a": 2, "b": 3})
    assert result == 5

@pytest.mark.asyncio
async def test_function_tool_arun_sync_fallback():
    """arun() on a sync function should work by calling it directly."""
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b
    tool = FunctionTool(add)
    result = await tool.arun(args={"a": 2, "b": 3})
    assert result == 5

@pytest.mark.asyncio
async def test_function_tool_arun_async():
    """arun() on an async function should await it."""
    async def fetch(url: str) -> str:
        """Fetch a URL."""
        return f"content from {url}"
    tool = FunctionTool(fetch)
    result = await tool.arun(args={"url": "https://example.com"})
    assert result == "content from https://example.com"

def test_function_tool_async_sync_run_raises():
    """Calling sync run() on an async function should raise TypeError."""
    async def fetch(url: str) -> str:
        """Fetch a URL."""
        return f"content from {url}"
    tool = FunctionTool(fetch)
    with pytest.raises(TypeError, match="Use arun"):
        tool.run(args={"url": "https://example.com"})

@pytest.mark.asyncio
async def test_function_tool_async_detection():
    """FunctionTool should correctly detect async functions."""
    async def async_fn() -> str:
        """Async function."""
        return "async"
    def sync_fn() -> str:
        """Sync function."""
        return "sync"
    assert FunctionTool(async_fn)._is_async is True
    assert FunctionTool(sync_fn)._is_async is False

def test_function_tool_schema():
    def search(query: str, limit: int = 10) -> str:
        """Search for something."""
        return f"results for {query}"
    tool = FunctionTool(search)
    schema = tool.get_schema()
    assert schema["name"] == "search"
    assert "query" in schema["parameters"]
