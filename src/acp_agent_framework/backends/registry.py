"""Backend registry for managing ACP agent configurations."""
from pydantic import BaseModel, Field

class BackendConfig(BaseModel):
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    timeout: float = Field(default=120.0, gt=0)
    max_retries: int = Field(default=3, ge=1)
    retry_base_delay: float = Field(default=1.0, ge=0)

DEFAULT_BACKENDS: dict[str, BackendConfig] = {
    "claude": BackendConfig(command="claude-agent-acp"),
    "gemini": BackendConfig(command="gemini", args=["--experimental-acp"]),
    "codex": BackendConfig(command="codex-acp"),
    "openai": BackendConfig(command="openai-acp"),
    "ollama": BackendConfig(command="ollama-acp"),
}

class BackendRegistry:
    _instance = None
    _backends: dict[str, BackendConfig] = {}

    def __new__(cls) -> "BackendRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._backends = dict(DEFAULT_BACKENDS)
        return cls._instance

    def register(self, name: str, config: BackendConfig) -> None:
        self._backends[name] = config

    def get(self, name: str) -> BackendConfig:
        if name not in self._backends:
            raise KeyError(f"Unknown backend: {name!r}. Available: {list(self._backends.keys())}")
        return self._backends[name]

    def list(self) -> list[str]:
        return list(self._backends.keys())
