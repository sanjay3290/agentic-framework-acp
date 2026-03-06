"""Lightweight observability module with structured JSON logging and basic tracing."""

import json
import logging
import os
from typing import Any, Optional

from acp_agent_framework.events import Event


class _JsonFormatter(logging.Formatter):
    """Formats log records as structured JSON."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": record.created,
            "level": record.levelname,
            "agent_name": getattr(record, "agent_name", None),
            "session_id": getattr(record, "session_id", None),
            "message": record.getMessage(),
        }
        extra = getattr(record, "extra_data", None)
        if extra:
            entry.update(extra)
        return json.dumps(entry, default=str)


class AgentLogger:
    """Structured JSON logger tailored for agent observability.

    Wraps Python's ``logging`` module and emits every log entry as a single-line
    JSON object containing *timestamp*, *level*, *agent_name*, *session_id*, and
    *message* fields.

    Use the module-level :func:`get_logger` helper to obtain an instance.
    """

    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(f"acp_agent.{name}")
        level_name = os.environ.get("AGENT_LOG_LEVEL", "INFO").upper()
        level = getattr(logging, level_name, logging.INFO)
        self._logger.setLevel(level)

        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(_JsonFormatter())
            self._logger.addHandler(handler)

        self._logger.propagate = False

    # -- public helpers -------------------------------------------------------

    def agent_start(self, agent_name: str, session_id: str) -> None:
        """Log agent run start."""
        self._emit(
            logging.INFO,
            f"Agent started: {agent_name}",
            agent_name=agent_name,
            session_id=session_id,
        )

    def agent_end(
        self, agent_name: str, session_id: str, duration_ms: float
    ) -> None:
        """Log agent run completion with elapsed time."""
        self._emit(
            logging.INFO,
            f"Agent finished: {agent_name} ({duration_ms:.1f}ms)",
            agent_name=agent_name,
            session_id=session_id,
            extra_data={"duration_ms": duration_ms},
        )

    def agent_error(self, agent_name: str, error: BaseException) -> None:
        """Log an agent-level error."""
        self._emit(
            logging.ERROR,
            f"Agent error: {agent_name} - {error}",
            agent_name=agent_name,
            extra_data={"error_type": type(error).__name__, "error": str(error)},
        )

    def tool_call(self, tool_name: str, args: Any) -> None:
        """Log a tool invocation."""
        self._emit(
            logging.DEBUG,
            f"Tool call: {tool_name}",
            extra_data={"tool_name": tool_name, "tool_args": args},
        )

    def tool_result(self, tool_name: str, result: Any) -> None:
        """Log a tool result."""
        self._emit(
            logging.DEBUG,
            f"Tool result: {tool_name}",
            extra_data={"tool_name": tool_name, "tool_result": result},
        )

    def skill_loaded(self, skill_name: str) -> None:
        """Log a skill being loaded."""
        self._emit(
            logging.INFO,
            f"Skill loaded: {skill_name}",
            extra_data={"skill_name": skill_name},
        )

    def event(self, event: Event) -> None:
        """Log an agent Event."""
        self._emit(
            logging.INFO,
            f"Event [{event.type}] from {event.author}",
            extra_data={
                "event_id": event.id,
                "event_type": event.type,
                "event_author": event.author,
            },
        )

    # -- internals ------------------------------------------------------------

    def _emit(
        self,
        level: int,
        message: str,
        *,
        agent_name: Optional[str] = None,
        session_id: Optional[str] = None,
        extra_data: Optional[dict[str, Any]] = None,
    ) -> None:
        if not self._logger.isEnabledFor(level):
            return
        record = self._logger.makeRecord(
            name=self._logger.name,
            level=level,
            fn="",
            lno=0,
            msg=message,
            args=(),
            exc_info=None,
        )
        record.agent_name = agent_name  # type: ignore[attr-defined]
        record.session_id = session_id  # type: ignore[attr-defined]
        record.extra_data = extra_data  # type: ignore[attr-defined]
        self._logger.handle(record)


def get_logger(name: str) -> AgentLogger:
    """Return an :class:`AgentLogger` for the given component *name*."""
    return AgentLogger(name)
