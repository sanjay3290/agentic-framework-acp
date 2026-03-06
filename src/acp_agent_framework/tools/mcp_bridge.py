"""MCP Bridge - wraps FunctionTools as an MCP stdio server for ACP backends."""
import json
import os
import sys
import tempfile
from typing import Any

from acp_agent_framework.tools.base import BaseTool


class McpBridge:
    """Manages an MCP server subprocess that exposes framework tools."""

    def __init__(self, tools: list[BaseTool]) -> None:
        self._tools = tools
        self._tools_file: str | None = None

    def _serialize_tools(self) -> list[dict[str, Any]]:
        """Serialize tools to JSON-compatible dicts with import info.

        Only FunctionTool instances with importable callables are supported.
        Other tool types (AgentTool, custom BaseTool) raise TypeError.
        """
        result = []
        for tool in self._tools:
            if not hasattr(tool, "_func"):
                raise TypeError(
                    f"Tool '{tool.name}' ({type(tool).__name__}) cannot be bridged to MCP. "
                    f"Only FunctionTool instances with importable callables are supported."
                )
            func = tool._func
            module = getattr(func, "__module__", None)
            qualname = getattr(func, "__qualname__", None)
            if not module or not qualname:
                raise TypeError(
                    f"Tool '{tool.name}' has a callable without __module__/__qualname__. "
                    f"It cannot be imported by the MCP server subprocess."
                )
            entry: dict[str, Any] = {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.get_schema().get("parameters", {}),
                "module": module,
                "qualname": qualname,
            }
            result.append(entry)
        return result

    def start(self) -> None:
        """Write tool definitions to a temp file for the MCP server."""
        tool_defs = self._serialize_tools()
        fd, path = tempfile.mkstemp(suffix=".json", prefix="acp_tools_")
        with os.fdopen(fd, "w") as f:
            json.dump(tool_defs, f)
        self._tools_file = path

    def get_mcp_config(self) -> Any:
        """Return an ACP McpServerStdio config pointing to our MCP server."""
        if not self._tools_file:
            raise RuntimeError("Bridge not started. Call start() first.")
        try:
            import acp
        except ImportError:
            raise RuntimeError("acp package required")

        return acp.schema.McpServerStdio(
            name="framework-tools",
            command=sys.executable,
            args=["-m", "acp_agent_framework.tools.mcp_tool_server", self._tools_file],
            env=[],
        )

    def stop(self) -> None:
        """Clean up temp files."""
        if self._tools_file and os.path.exists(self._tools_file):
            os.unlink(self._tools_file)
            self._tools_file = None
