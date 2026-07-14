"""Execution context passed through agent pipelines."""
import asyncio
from typing import Any, Optional
from acp_agent_framework.state import State

class Context:
    def __init__(self, session_id: str, cwd: str, state: Optional[State] = None):
        self.session_id = session_id
        self.cwd = cwd
        self.state = state or State()
        self._input: Any = None
        self._output: Any = None
        self._agent_outputs: dict[str, Any] = {}
        self._history: list[dict[str, str]] = []
        self._resources: dict[str, Any] = {}
        self._resource_locks: dict[str, asyncio.Lock] = {}

    def add_message(self, role: str, content: str) -> None:
        """Add a message to conversation history."""
        self._history.append({"role": role, "content": content})

    def get_history(self) -> list[dict[str, str]]:
        """Get conversation history."""
        return list(self._history)

    def clear_history(self) -> None:
        """Clear conversation history."""
        self._history.clear()

    def get_resource(self, key: str) -> Any:
        return self._resources.get(key)

    def set_resource(self, key: str, value: Any) -> None:
        self._resources[key] = value

    def pop_resource(self, key: str) -> Any:
        return self._resources.pop(key, None)

    def resource_lock(self, key: str) -> asyncio.Lock:
        """Return a per-key lock for resource creation/use (created lazily)."""
        lock = self._resource_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._resource_locks[key] = lock
        return lock

    async def close(self) -> None:
        """Release all session resources (backend processes, bridges)."""
        first_error: Exception | None = None
        for key, res in list(self._resources.items()):
            closer = getattr(res, "aclose", None)
            if closer is not None:
                try:
                    await closer()
                except Exception as e:
                    if first_error is None:
                        first_error = e
        self._resources.clear()
        self._resource_locks.clear()
        if first_error is not None:
            raise first_error

    def get_input(self) -> Any:
        return self._input

    def set_input(self, value: Any) -> None:
        self._input = value

    def get_output(self) -> Any:
        return self._output

    def set_output(self, value: Any) -> None:
        self._output = value

    def set_agent_output(self, agent_name: str, output: Any) -> None:
        self._agent_outputs[agent_name] = output

    def get_agent_output(self, agent_name: str) -> Optional[Any]:
        return self._agent_outputs.get(agent_name)
