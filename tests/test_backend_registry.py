import pytest
from acp_agent_framework.backends.registry import BackendConfig, BackendRegistry

def test_default_backends_registered():
    registry = BackendRegistry()
    assert "claude" in registry.list()
    assert "gemini" in registry.list()
    assert "codex" in registry.list()
    assert "openai" in registry.list()
    assert "ollama" in registry.list()

def test_get_backend_config():
    registry = BackendRegistry()
    config = registry.get("claude")
    assert config.command == "claude-agent-acp"

def test_register_custom_backend():
    registry = BackendRegistry()
    registry.register("my-agent", BackendConfig(command="/usr/local/bin/my-agent", args=["--acp"]))
    assert "my-agent" in registry.list()
    config = registry.get("my-agent")
    assert config.command == "/usr/local/bin/my-agent"
    assert config.args == ["--acp"]

def test_openai_backend_config():
    registry = BackendRegistry()
    config = registry.get("openai")
    assert config.command == "openai-acp"
    assert config.args == []

def test_ollama_backend_config():
    registry = BackendRegistry()
    config = registry.get("ollama")
    assert config.command == "ollama-acp"
    assert config.args == []

def test_get_unknown_backend_raises():
    registry = BackendRegistry()
    with pytest.raises(KeyError):
        registry.get("nonexistent")
