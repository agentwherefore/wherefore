import json

from .paths import CONFIG_DIR

CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    # TR-2: single local-config setting selects the Claude access engine.
    "claude_engine": "api_key",  # "api_key" | "claude_code_cli"
    # TR-4: only ever read from this git-ignored file, never from a DB record.
    "anthropic_api_key": "",
}


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return dict(DEFAULT_CONFIG)
    with CONFIG_PATH.open() as f:
        data = json.load(f)
    return {**DEFAULT_CONFIG, **data}
