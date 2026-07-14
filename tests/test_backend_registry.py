import pytest
from acp_agent_framework.backends.registry import BackendConfig, BackendRegistry

def test_default_backends_registered():
    registry = BackendRegistry()
    backends = registry.list()
    assert "claude" in backends
    assert "gemini" in backends
    assert "codex" in backends
    assert "copilot" in backends
    assert "opencode" in backends
    assert "goose" in backends
    assert "qwen" in backends
    assert "cursor" in backends
    assert "grok" in backends
    assert "cline" in backends
    assert "auggie" in backends
    assert "kilo" in backends
    assert "devin" in backends
    assert "kimi" in backends
    assert "openai" not in backends
    assert "ollama" not in backends

def test_get_backend_config():
    registry = BackendRegistry()
    config = registry.get("claude")
    assert config.command == "claude-agent-acp"

def test_gemini_backend_config():
    registry = BackendRegistry()
    config = registry.get("gemini")
    assert config.command == "gemini"
    assert config.args == ["--acp"]

def test_codex_backend_config():
    registry = BackendRegistry()
    config = registry.get("codex")
    assert config.command == "codex-acp"
    assert config.args == []

def test_new_default_backend_configs():
    registry = BackendRegistry()
    copilot = registry.get("copilot")
    assert copilot.command == "copilot"
    assert copilot.args == ["--acp"]
    grok = registry.get("grok")
    assert grok.command == "grok"
    assert grok.args == ["agent", "stdio"]
    opencode = registry.get("opencode")
    assert opencode.command == "opencode"
    assert opencode.args == ["acp"]


def test_register_custom_backend():
    registry = BackendRegistry()
    registry.register("my-agent", BackendConfig(command="/usr/local/bin/my-agent", args=["--acp"]))
    assert "my-agent" in registry.list()
    config = registry.get("my-agent")
    assert config.command == "/usr/local/bin/my-agent"
    assert config.args == ["--acp"]

def test_get_unknown_backend_raises():
    registry = BackendRegistry()
    with pytest.raises(KeyError):
        registry.get("nonexistent")
