"""Integration tests for ACP backends.

These tests require actual backend agents installed:
- Claude: claude-agent-acp (npm: @zed-industries/claude-agent-acp)
- Gemini: gemini (npm: @google/gemini-cli)
- Codex: npx @zed-industries/codex-acp

Run with: pytest tests/integration/ -v -m integration
"""
import shutil
import pytest
from acp_agent_framework.backends.acp_backend import AcpBackend
from acp_agent_framework.backends.registry import BackendRegistry


def _backend_available(command: str) -> bool:
    return shutil.which(command) is not None


registry = BackendRegistry()


@pytest.mark.integration
@pytest.mark.skipif(not _backend_available("claude-agent-acp"), reason="claude-agent-acp not installed")
@pytest.mark.asyncio
async def test_claude_acp_handshake():
    config = registry.get("claude")
    backend = AcpBackend(config)
    try:
        await backend.start()
        session_id = await backend.new_session("/tmp/test")
        assert session_id is not None
        assert len(session_id) > 0
    finally:
        await backend.stop()


@pytest.mark.integration
@pytest.mark.skipif(not _backend_available("claude-agent-acp"), reason="claude-agent-acp not installed")
@pytest.mark.asyncio
async def test_claude_prompt_response():
    config = registry.get("claude")
    backend = AcpBackend(config)
    try:
        await backend.start()
        session_id = await backend.new_session("/tmp/test")
        response = await backend.prompt(session_id, "Say hello in exactly one word.")
        assert response is not None
        assert len(response) > 0
    finally:
        await backend.stop()


@pytest.mark.integration
@pytest.mark.skipif(not _backend_available("gemini"), reason="gemini CLI not installed")
@pytest.mark.asyncio
async def test_gemini_acp_handshake():
    config = registry.get("gemini")
    backend = AcpBackend(config)
    try:
        await backend.start()
        session_id = await backend.new_session("/tmp/test")
        assert session_id is not None
    finally:
        await backend.stop()


@pytest.mark.integration
@pytest.mark.skipif(not _backend_available("npx"), reason="npx not installed")
@pytest.mark.asyncio
async def test_codex_acp_handshake():
    config = registry.get("codex")
    backend = AcpBackend(config)
    try:
        await backend.start()
        session_id = await backend.new_session("/tmp/test")
        assert session_id is not None
    finally:
        await backend.stop()
