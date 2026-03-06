"""Session persistence - JSON file storage for v1."""
import json
from pathlib import Path
from typing import Any, Optional

class JsonSessionStore:
    def __init__(self, storage_dir: Path) -> None:
        self._dir = Path(storage_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        if not session_id or "/" in session_id or "\\" in session_id or ".." in session_id:
            raise ValueError(
                f"Invalid session_id: {session_id!r}. "
                "Must not contain path separators or '..'."
            )
        resolved = (self._dir / f"{session_id}.json").resolve()
        if not str(resolved).startswith(str(self._dir.resolve())):
            raise ValueError(f"Session ID escapes storage directory: {session_id!r}")
        return resolved

    def save(self, session_id: str, data: dict[str, Any]) -> None:
        self._path(session_id).write_text(json.dumps(data, default=str))

    def load(self, session_id: str) -> Optional[dict[str, Any]]:
        path = self._path(session_id)
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def delete(self, session_id: str) -> None:
        path = self._path(session_id)
        if path.exists():
            path.unlink()

    def list_sessions(self) -> list[str]:
        return [p.stem for p in self._dir.glob("*.json")]
