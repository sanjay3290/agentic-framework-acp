"""Session state management with delta tracking."""
from typing import Any, Optional

class State:
    def __init__(self, initial: Optional[dict[str, Any]] = None):
        self._data: dict[str, Any] = dict(initial or {})
        self._delta: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._delta:
            return self._delta[key]
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._delta[key] = value

    def get_delta(self) -> dict[str, Any]:
        return dict(self._delta)

    def commit(self) -> None:
        self._delta.clear()

    def get_persistable(self) -> dict[str, Any]:
        return {k: v for k, v in self._data.items() if not k.startswith("temp:")}

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)
