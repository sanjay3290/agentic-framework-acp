import pytest
from pydantic import ValidationError
from acp_agent_framework.backends.acp_backend import AcpBackend
from acp_agent_framework.backends.registry import BackendConfig

def test_acp_backend_creation():
    config = BackendConfig(command="echo", args=["hello"])
    backend = AcpBackend(config)
    assert backend.config == config
    assert not backend.is_running

@pytest.mark.asyncio
async def test_acp_backend_spawn_invalid_command():
    config = BackendConfig(command="nonexistent-command-12345")
    backend = AcpBackend(config)
    with pytest.raises(Exception):
        await backend.start()


def test_backend_config_rejects_invalid_timeout():
    with pytest.raises(ValidationError):
        BackendConfig(command="echo", timeout=0)
    with pytest.raises(ValidationError):
        BackendConfig(command="echo", timeout=-1)


def test_backend_config_rejects_invalid_retries():
    with pytest.raises(ValidationError):
        BackendConfig(command="echo", max_retries=0)
    with pytest.raises(ValidationError):
        BackendConfig(command="echo", max_retries=-1)


def test_backend_config_rejects_negative_delay():
    with pytest.raises(ValidationError):
        BackendConfig(command="echo", retry_base_delay=-0.5)
