class ExtractionError(Exception):
    """Base error for extraction engine failures."""


class SchemaValidationError(ExtractionError):
    """Raised when an engine's output can't be validated against the shared schema."""


class ClaudeSessionExpiredError(ExtractionError):
    """Raised when the Claude Code CLI subprocess fails because the session has expired."""
