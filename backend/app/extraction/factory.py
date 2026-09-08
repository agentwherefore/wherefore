from ..config import load_config
from .api_key_engine import APIKeyEngine
from .base import ExtractionEngine
from .claude_cli_engine import ClaudeCodeCLIEngine


def get_engine() -> ExtractionEngine:
    """Selected by TR-2's config setting. Callers never branch on which
    engine they got — both implement the same ExtractionEngine interface."""
    engine_name = load_config().get("claude_engine", "api_key")
    if engine_name == "claude_code_cli":
        return ClaudeCodeCLIEngine()
    if engine_name == "api_key":
        return APIKeyEngine()
    raise ValueError(f"Unknown claude_engine config value: {engine_name!r}")
