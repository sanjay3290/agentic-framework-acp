"""ACP backend client - spawns and communicates with ACP agents."""
import asyncio
import os
from pathlib import Path
from typing import Any, AsyncGenerator, Optional
import acp
from acp_agent_framework.backends.registry import BackendConfig


class _MinimalClient:
    def __init__(self, sandbox_root: Optional[str] = None) -> None:
        self.updates: list[Any] = []
        self._sandbox_root = Path(sandbox_root).resolve() if sandbox_root else None

    def _validate_path(self, path: str) -> Path:
        """Validate path stays within sandbox root."""
        resolved = Path(path).resolve()
        if self._sandbox_root and not str(resolved).startswith(str(self._sandbox_root)):
            raise acp.RequestError(
                -32002, "Access denied: path escapes sandbox root"
            )
        return resolved

    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        self.updates.append(update)

    async def request_permission(self, options: Any, session_id: str, tool_call: Any, **kwargs: Any) -> Any:
        option_id = options[0].option_id if options else "allow_once"
        return acp.schema.RequestPermissionResponse(
            outcome=acp.schema.AllowedOutcome(outcome="selected", option_id=option_id),
        )

    async def read_text_file(self, path: str, session_id: str, limit: Any = None, line: Any = None, **kwargs: Any) -> Any:
        resolved = self._validate_path(path)
        try:
            content = resolved.read_text()
            return acp.schema.ReadTextFileResponse(content=content)
        except FileNotFoundError:
            raise acp.RequestError(-32002, f"File not found: {path}")

    async def write_text_file(self, content: str, path: str, session_id: str, **kwargs: Any) -> None:
        resolved = self._validate_path(path)
        resolved.write_text(content)

    async def create_terminal(self, command: str, session_id: str, **kwargs: Any) -> Any:
        raise acp.RequestError(-32601, "Terminal not supported")

    async def terminal_output(self, session_id: str, terminal_id: str, **kwargs: Any) -> Any:
        raise acp.RequestError(-32601, "Terminal not supported")

    async def wait_for_terminal_exit(self, session_id: str, terminal_id: str, **kwargs: Any) -> Any:
        raise acp.RequestError(-32601, "Terminal not supported")

    async def kill_terminal(self, session_id: str, terminal_id: str, **kwargs: Any) -> Any:
        raise acp.RequestError(-32601, "Terminal not supported")

    async def release_terminal(self, session_id: str, terminal_id: str, **kwargs: Any) -> Any:
        raise acp.RequestError(-32601, "Terminal not supported")

    def on_connect(self, conn: Any) -> None:
        pass

    async def ext_method(self, name: str, payload: Any) -> Any:
        raise acp.RequestError(-32601, f"Extension method not supported: {name}")

    async def ext_notification(self, name: str, payload: Any) -> None:
        pass


class AcpBackend:
    def __init__(self, config: BackendConfig, sandbox_root: Optional[str] = None) -> None:
        self.config = config
        self._sandbox_root = sandbox_root
        self._process: Optional[asyncio.subprocess.Process] = None
        self._connection: Optional[acp.connection.ClientSideConnection] = None
        self._client = _MinimalClient(sandbox_root)

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def start(self) -> None:
        env_args = {}
        if self.config.env:
            env_args["env"] = {**os.environ, **self.config.env}

        # Disable filesystem capabilities when no sandbox root is set
        fs_cap = None
        if self._sandbox_root:
            fs_cap = acp.schema.FileSystemCapability(
                read_text_file=True, write_text_file=True
            )

        self._process = await asyncio.create_subprocess_exec(
            self.config.command, *self.config.args,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, **env_args,
        )
        self._connection = acp.connect_to_agent(
            self._client, self._process.stdin, self._process.stdout,
        )
        await self._connection.initialize(
            protocol_version=acp.PROTOCOL_VERSION,
            client_capabilities=acp.schema.ClientCapabilities(fs=fs_cap),
            client_info=acp.schema.Implementation(
                name="acp-agent-framework", version="0.1.0"
            ),
        )

    async def new_session(self, cwd: str, mcp_servers: Optional[list] = None) -> str:
        if not self._connection:
            raise RuntimeError("Backend not started. Call start() first.")
        result = await self._connection.new_session(
            cwd=cwd, mcp_servers=mcp_servers or []
        )
        return result.session_id

    async def _do_prompt(self, session_id: str, text: str) -> str:
        """Execute a single prompt request without retries."""
        if not self._connection:
            raise RuntimeError("Backend not started.")
        self._client.updates.clear()
        await asyncio.wait_for(
            self._connection.prompt(
                session_id=session_id,
                prompt=[acp.schema.TextContentBlock(type="text", text=text)],
            ),
            timeout=self.config.timeout,
        )
        return self._collect_response_text()

    def _collect_response_text(self) -> str:
        """Extract text from accumulated session updates."""
        collected = []
        for update in self._client.updates:
            # Handle nested content blocks (AgentMessageChunk.content.text)
            if hasattr(update, "content") and hasattr(update.content, "text"):
                collected.append(update.content.text)
            elif hasattr(update, "text"):
                collected.append(update.text)
        return "".join(collected)

    async def prompt(self, session_id: str, text: str) -> str:
        """Prompt with retry logic and timeout."""
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries):
            try:
                return await self._do_prompt(session_id, text)
            except (asyncio.TimeoutError, ConnectionError, OSError) as e:
                last_error = e
                if attempt < self.config.max_retries - 1:
                    delay = self.config.retry_base_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
        raise RuntimeError(
            f"Backend prompt failed after {self.config.max_retries} attempts"
        ) from last_error

    async def prompt_stream(self, session_id: str, text: str) -> AsyncGenerator[str, None]:
        """Prompt and yield text chunks as they arrive via session updates."""
        if not self._connection:
            raise RuntimeError("Backend not started.")
        self._client.updates.clear()
        await asyncio.wait_for(
            self._connection.prompt(
                session_id=session_id,
                prompt=[acp.schema.TextContentBlock(type="text", text=text)],
            ),
            timeout=self.config.timeout,
        )
        for update in self._client.updates:
            if hasattr(update, "content") and hasattr(update.content, "text"):
                yield update.content.text
            elif hasattr(update, "text"):
                yield update.text

    async def stop(self) -> None:
        if self._connection:
            await self._connection.close()
            self._connection = None
        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
            self._process = None
