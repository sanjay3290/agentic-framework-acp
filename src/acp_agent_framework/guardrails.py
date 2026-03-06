"""Guardrails for input/output validation on agent prompts and responses."""
from typing import Callable, Optional


class GuardrailError(Exception):
    """Raised when a guardrail validation fails."""

    def __init__(self, message: str, guardrail_name: str = ""):
        self.guardrail_name = guardrail_name
        super().__init__(message)


class Guardrail:
    """A named validation function that can be applied before prompt or after response."""

    def __init__(self, name: str, fn: Callable[[str], Optional[str]]):
        self.name = name
        self._fn = fn

    def validate(self, text: str) -> str:
        """Validate text. Returns transformed text or raises GuardrailError."""
        result = self._fn(text)
        if result is None:
            return text
        return result
