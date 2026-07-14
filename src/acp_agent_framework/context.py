"""Execution context passed through agent pipelines."""
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

    async def close(self) -> None:
        """Release all session resources (backend processes, bridges)."""
        for key, res in list(self._resources.items()):
            closer = getattr(res, "aclose", None)
            if closer is not None:
                await closer()
        self._resources.clear()

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
