"""Tests for the observability module."""

import json
import logging
import os
from unittest import mock

from acp_agent_framework.observability import AgentLogger, get_logger
from acp_agent_framework.events import Event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _CaptureHandler(logging.Handler):
    """Stores formatted log records for assertion."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(self.format(record))


def _make_logger(name: str = "test", level: int = logging.DEBUG) -> tuple[AgentLogger, _CaptureHandler]:
    """Create an AgentLogger with a capture handler attached."""
    logger = get_logger(name)
    # Replace handlers with our capture handler using the same formatter
    inner = logger._logger
    formatter = inner.handlers[0].formatter if inner.handlers else None
    capture = _CaptureHandler()
    if formatter:
        capture.setFormatter(formatter)
    inner.handlers = [capture]
    inner.setLevel(level)
    return logger, capture


def _parse_last(capture: _CaptureHandler) -> dict:
    """Parse the most recent captured log line as JSON."""
    assert capture.records, "No log records captured"
    return json.loads(capture.records[-1])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLoggerCreation:
    def test_get_logger_returns_agent_logger(self) -> None:
        logger = get_logger("myagent")
        assert isinstance(logger, AgentLogger)

    def test_get_logger_uses_acp_namespace(self) -> None:
        logger = get_logger("foo")
        assert logger._logger.name == "acp_agent.foo"

    def test_default_log_level_is_info(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AGENT_LOG_LEVEL", None)
            logger = AgentLogger("default_level_test")
            assert logger._logger.level == logging.INFO

    def test_env_var_sets_log_level(self) -> None:
        with mock.patch.dict(os.environ, {"AGENT_LOG_LEVEL": "DEBUG"}):
            logger = AgentLogger("env_level_test")
            assert logger._logger.level == logging.DEBUG


class TestStructuredOutput:
    def test_log_entry_is_valid_json(self) -> None:
        logger, capture = _make_logger("json_test")
        logger.agent_start("a1", "s1")
        entry = _parse_last(capture)
        assert isinstance(entry, dict)

    def test_log_entry_has_required_fields(self) -> None:
        logger, capture = _make_logger("fields_test")
        logger.agent_start("a1", "s1")
        entry = _parse_last(capture)
        assert "timestamp" in entry
        assert "level" in entry
        assert "agent_name" in entry
        assert "session_id" in entry
        assert "message" in entry

    def test_agent_name_and_session_propagated(self) -> None:
        logger, capture = _make_logger("prop_test")
        logger.agent_start("my_agent", "sess_42")
        entry = _parse_last(capture)
        assert entry["agent_name"] == "my_agent"
        assert entry["session_id"] == "sess_42"


class TestLogLevelFiltering:
    def test_debug_filtered_at_info_level(self) -> None:
        logger, capture = _make_logger("filter_test", level=logging.INFO)
        logger.tool_call("t1", {"x": 1})  # DEBUG level
        assert len(capture.records) == 0

    def test_debug_passes_at_debug_level(self) -> None:
        logger, capture = _make_logger("filter_test2", level=logging.DEBUG)
        logger.tool_call("t1", {"x": 1})
        assert len(capture.records) == 1


class TestLogMethods:
    def test_agent_start(self) -> None:
        logger, capture = _make_logger("m1")
        logger.agent_start("agent_a", "s1")
        entry = _parse_last(capture)
        assert entry["level"] == "INFO"
        assert "agent_a" in entry["message"]

    def test_agent_end(self) -> None:
        logger, capture = _make_logger("m2")
        logger.agent_end("agent_a", "s1", 123.4)
        entry = _parse_last(capture)
        assert entry["level"] == "INFO"
        assert entry["duration_ms"] == 123.4

    def test_agent_error(self) -> None:
        logger, capture = _make_logger("m3")
        logger.agent_error("agent_a", ValueError("boom"))
        entry = _parse_last(capture)
        assert entry["level"] == "ERROR"
        assert entry["error_type"] == "ValueError"
        assert entry["error"] == "boom"

    def test_tool_call(self) -> None:
        logger, capture = _make_logger("m4")
        logger.tool_call("my_tool", {"key": "val"})
        entry = _parse_last(capture)
        assert entry["tool_name"] == "my_tool"
        assert entry["tool_args"] == {"key": "val"}

    def test_tool_result(self) -> None:
        logger, capture = _make_logger("m5")
        logger.tool_result("my_tool", "ok")
        entry = _parse_last(capture)
        assert entry["tool_name"] == "my_tool"
        assert entry["tool_result"] == "ok"

    def test_skill_loaded(self) -> None:
        logger, capture = _make_logger("m6")
        logger.skill_loaded("code_review")
        entry = _parse_last(capture)
        assert entry["level"] == "INFO"
        assert entry["skill_name"] == "code_review"

    def test_event(self) -> None:
        logger, capture = _make_logger("m7")
        evt = Event(author="bot", type="message", content="hello")
        logger.event(evt)
        entry = _parse_last(capture)
        assert entry["level"] == "INFO"
        assert entry["event_type"] == "message"
        assert entry["event_author"] == "bot"
        assert "event_id" in entry
