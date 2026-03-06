import json
import os
import pytest
from acp_agent_framework.tools.base import BaseTool
from acp_agent_framework.tools.function_tool import FunctionTool
from acp_agent_framework.tools.mcp_bridge import McpBridge


def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


def greet(name: str) -> str:
    """Greet someone."""
    return f"Hello, {name}!"


def test_bridge_serialize_tools():
    tools = [FunctionTool(add), FunctionTool(greet)]
    bridge = McpBridge(tools)
    serialized = bridge._serialize_tools()
    assert len(serialized) == 2
    assert serialized[0]["name"] == "add"
    assert serialized[0]["description"] == "Add two numbers."
    assert serialized[0]["module"] is not None
    assert serialized[0]["qualname"] == "add"
    assert serialized[1]["name"] == "greet"


def test_bridge_start_creates_temp_file():
    tools = [FunctionTool(add)]
    bridge = McpBridge(tools)
    bridge.start()
    assert bridge._tools_file is not None
    assert os.path.exists(bridge._tools_file)
    with open(bridge._tools_file) as f:
        data = json.load(f)
    assert len(data) == 1
    assert data[0]["name"] == "add"
    bridge.stop()


def test_bridge_stop_cleans_up():
    tools = [FunctionTool(add)]
    bridge = McpBridge(tools)
    bridge.start()
    temp_path = bridge._tools_file
    assert os.path.exists(temp_path)
    bridge.stop()
    assert not os.path.exists(temp_path)
    assert bridge._tools_file is None


def test_bridge_get_mcp_config():
    tools = [FunctionTool(add)]
    bridge = McpBridge(tools)
    bridge.start()
    config = bridge.get_mcp_config()
    assert config.name == "framework-tools"
    assert config.command.endswith("python") or "python" in config.command
    assert "-m" in config.args
    assert "acp_agent_framework.tools.mcp_tool_server" in config.args
    assert bridge._tools_file in config.args
    bridge.stop()


def test_bridge_get_config_before_start_raises():
    tools = [FunctionTool(add)]
    bridge = McpBridge(tools)
    with pytest.raises(RuntimeError, match="not started"):
        bridge.get_mcp_config()


def test_bridge_rejects_non_function_tool():
    """Non-FunctionTool instances (e.g. BaseTool subclasses) should raise TypeError."""
    class CustomTool(BaseTool):
        name = "custom"
        description = "A custom tool"
        def run(self, args):
            return "result"
        def get_schema(self):
            return {"name": self.name, "parameters": {}}

    bridge = McpBridge([CustomTool()])
    with pytest.raises(TypeError, match="cannot be bridged"):
        bridge._serialize_tools()
