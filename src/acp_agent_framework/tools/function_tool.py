"""Wrap a Python callable as a tool with auto-extracted schema."""
import asyncio
import inspect
from typing import Any, Callable
from acp_agent_framework.tools.base import BaseTool

class FunctionTool(BaseTool):
    def __init__(self, func: Callable) -> None:
        self._func = func
        self.name = func.__name__
        self.description = (func.__doc__ or "").strip()
        self._sig = inspect.signature(func)
        self._is_async = inspect.iscoroutinefunction(func)

    def run(self, args: dict[str, Any]) -> Any:
        """Execute the tool synchronously. Raises TypeError for async functions."""
        if self._is_async:
            raise TypeError(
                f"Cannot call sync run() on async function '{self.name}'. Use arun() instead."
            )
        return self._func(**args)

    async def arun(self, args: dict[str, Any]) -> Any:
        """Execute the tool asynchronously. Awaits async functions, offloads sync to thread."""
        if self._is_async:
            return await self._func(**args)
        return await asyncio.to_thread(self._func, **args)

    def get_schema(self) -> dict[str, Any]:
        params: dict[str, Any] = {}
        for param_name, param in self._sig.parameters.items():
            param_info: dict[str, Any] = {}
            if param.annotation != inspect.Parameter.empty:
                param_info["type"] = param.annotation.__name__
            if param.default != inspect.Parameter.empty:
                param_info["default"] = param.default
            params[param_name] = param_info
        return {"name": self.name, "description": self.description, "parameters": params}
