"""Standalone MCP stdio server that exposes framework tools.

This script is spawned as a subprocess by McpBridge. It reads tool
definitions from a JSON file and registers them with FastMCP.

Usage: python -m acp_agent_framework.tools.mcp_tool_server <tools.json>
"""
import importlib
import json
import sys


def _import_callable(module_path: str, qualname: str):
    """Import a callable from module path and qualified name."""
    mod = importlib.import_module(module_path)
    obj = mod
    for attr in qualname.split("."):
        obj = getattr(obj, attr)
    return obj



def main():
    if len(sys.argv) < 2:
        print("Usage: python -m acp_agent_framework.tools.mcp_tool_server <tools.json>", file=sys.stderr)
        sys.exit(1)

    tools_file = sys.argv[1]
    with open(tools_file) as f:
        tool_defs = json.load(f)

    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        print("Error: mcp package required. Install with: pip install mcp", file=sys.stderr)
        sys.exit(1)

    mcp = FastMCP("acp-agent-framework-tools")

    for tool_def in tool_defs:
        name = tool_def["name"]
        description = tool_def.get("description", "")
        module_path = tool_def.get("module")
        qualname = tool_def.get("qualname")

        if not module_path or not qualname:
            print(
                f"Error: Tool '{name}' has no import metadata (module/qualname). "
                f"Only FunctionTool instances are supported via MCP bridge.",
                file=sys.stderr,
            )
            sys.exit(1)

        try:
            func = _import_callable(module_path, qualname)
        except (ImportError, AttributeError) as e:
            print(f"Error: Failed to import tool '{name}' from {module_path}.{qualname}: {e}", file=sys.stderr)
            sys.exit(1)

        mcp.tool(name=name, description=description)(func)

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
