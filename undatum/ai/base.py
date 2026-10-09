"""Errors raised by the AI helpers."""

from ..common.errors import UndatumError


class AIServiceError(UndatumError):
    """Base exception for AI service errors (an external service: exit code 3)."""

    code = "ai_error"

    def __init__(self, message: str, context: dict | None = None, exit_code: int = 3):
        super().__init__(message, context=context, exit_code=exit_code)


class AIConfigurationError(AIServiceError):
    """The AI provider is missing or misconfigured."""


class AIAPIError(AIServiceError):
    """A request to the AI provider failed or returned an unusable answer."""

    def __init__(self, message: str, status_code: int | None = None, response: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response
