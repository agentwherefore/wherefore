"""Validate both ExtractionEngine implementations against the canonical
fixture (technical spec build order, steps 5-6).

Runs ClaudeCodeCLIEngine always (uses the local `claude` CLI session).
Runs APIKeyEngine only if an API key is configured (config/config.json or
ANTHROPIC_API_KEY) — otherwise reports why it was skipped instead of failing.
When both ran, prints a side-by-side comparison of field names to eyeball
agreement between engines on the same input.

Usage: python3 scripts/validate_extraction.py   (run from backend/, venv active)
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_config  # noqa: E402
from app.extraction.api_key_engine import APIKeyEngine  # noqa: E402
from app.extraction.claude_cli_engine import ClaudeCodeCLIEngine  # noqa: E402
from app.extraction.errors import ExtractionError  # noqa: E402

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "acme"
TRANSCRIPT_PATH = FIXTURES_DIR / "transcript.txt"
SCREENSHOTS = [FIXTURES_DIR / "intake-form.png", FIXTURES_DIR / "caller-detail-sheet.png"]


def _print_fields(label: str, fields: list) -> None:
    print(f"\n--- {label}: {len(fields)} field(s) ---")
    for f in fields:
        flag = f" [{f.status}:{f.review_reason}]" if f.status == "needs_review" else ""
        print(f"  {f.entity:<10} {f.section:<18} {f.name:<18} {f.field_type:<12}{flag}")


def _print_rules(label: str, rules: list) -> None:
    print(f"\n--- {label}: {len(rules)} rule(s) ---")
    for r in rules:
        flag = f" [{r.status}:{r.review_reason}]" if r.status == "needs_review" else ""
        print(f"  {r.source_detail:<8} {r.rule_type:<14} {r.description}{flag}")


async def run_engine(label: str, engine) -> dict:
    result = {"fields": [], "rules": [], "error": None}
    transcript_text = TRANSCRIPT_PATH.read_text()
    try:
        for screenshot in SCREENSHOTS:
            result["fields"] += await engine.extract_fields(str(screenshot), transcript_text)
        result["rules"] = await engine.extract_rules(transcript_text)
    except ExtractionError as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


async def main() -> None:
    config = load_config()
    have_api_key = bool(config.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY"))

    results = {}

    print("=" * 60)
    print("ClaudeCodeCLIEngine")
    print("=" * 60)
    cli_result = await run_engine("ClaudeCodeCLIEngine", ClaudeCodeCLIEngine())
    results["cli"] = cli_result
    if cli_result["error"]:
        print(f"FAILED: {cli_result['error']}")
    else:
        _print_fields("ClaudeCodeCLIEngine fields", cli_result["fields"])
        _print_rules("ClaudeCodeCLIEngine rules", cli_result["rules"])

    print("\n" + "=" * 60)
    print("APIKeyEngine")
    print("=" * 60)
    if not have_api_key:
        print("SKIPPED — no anthropic_api_key in config/config.json and no ANTHROPIC_API_KEY env var.")
        results["api"] = None
    else:
        api_result = await run_engine("APIKeyEngine", APIKeyEngine())
        results["api"] = api_result
        if api_result["error"]:
            print(f"FAILED: {api_result['error']}")
        else:
            _print_fields("APIKeyEngine fields", api_result["fields"])
            _print_rules("APIKeyEngine rules", api_result["rules"])

    if results.get("api") and not results["api"]["error"] and not cli_result["error"]:
        print("\n" + "=" * 60)
        print("Comparison — field names found by each engine")
        print("=" * 60)
        cli_names = {f.name for f in cli_result["fields"]}
        api_names = {f.name for f in results["api"]["fields"]}
        print(f"  Both engines:      {sorted(cli_names & api_names)}")
        print(f"  CLI only:          {sorted(cli_names - api_names)}")
        print(f"  API only:          {sorted(api_names - cli_names)}")


if __name__ == "__main__":
    asyncio.run(main())
