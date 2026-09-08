import asyncio
import json
from pathlib import Path
from typing import List, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from ..paths import UPLOAD_DIR
from .base import ExtractionEngine
from .errors import ClaudeSessionExpiredError, SchemaValidationError
from .prompts import (
    EXISTING_FIELDS_CONTEXT_PREFIX,
    EXISTING_FIELDS_CONTEXT_SUFFIX,
    EXISTING_RBP_CONTEXT_PREFIX,
    EXISTING_RBP_CONTEXT_SUFFIX,
    FIELD_EXTRACTION_INSTRUCTIONS,
    PROCESS_FLOW_GENERATION_INSTRUCTIONS,
    RBP_GENERATION_INSTRUCTIONS,
    RULE_EXTRACTION_INSTRUCTIONS,
    STORY_GENERATION_INSTRUCTIONS,
    TRANSCRIPT_CONTEXT_PREFIX,
    TRANSCRIPT_FIELD_EXTRACTION_INSTRUCTIONS,
)
from .schemas import (
    FIELDS_SCHEMA,
    PROCESS_FLOW_SCHEMA,
    RBP_SCHEMA,
    RULES_SCHEMA,
    STORIES_SCHEMA,
    FieldCandidate,
    ProcessFlow,
    ProcessStep,
    ProcessTransition,
    RbpEntry,
    Rule,
    StoryItem,
)

STRICTER_RETRY_SUFFIX = (
    "\n\nYour previous response did not validate against the required JSON "
    "schema. Re-read the instructions and produce output that matches it exactly."
)

T = TypeVar("T", bound=BaseModel)


class ClaudeCodeCLIEngine(ExtractionEngine):
    """Async subprocess call to `claude -p` (technical spec §5).

    Uses `claude -p --output-format json --json-schema <schema>`, which
    validates the response against a JSON Schema server-side and returns it
    pre-parsed in `structured_output` — a real schema guarantee from the CLI
    itself. Still retries once with a stricter prompt if the call doesn't
    come back as a validated success, and raises a clear error (not a raw
    subprocess failure) when the session has expired.
    """

    async def extract_fields(
        self,
        screenshot_path: str,
        transcript_context: Optional[str] = None,
        existing_fields_context: Optional[str] = None,
    ) -> List[FieldCandidate]:
        path = Path(screenshot_path).resolve()
        prompt = f"Read the image file at '{path}' and extract field candidates from it.\n\n" + FIELD_EXTRACTION_INSTRUCTIONS
        if transcript_context:
            prompt += "\n\n" + TRANSCRIPT_CONTEXT_PREFIX + transcript_context
        if existing_fields_context:
            prompt += "\n\n" + EXISTING_FIELDS_CONTEXT_PREFIX + existing_fields_context + EXISTING_FIELDS_CONTEXT_SUFFIX
        raw = await self._run_with_retry(prompt, FIELDS_SCHEMA)
        return self._validate_all(raw["fields"], FieldCandidate)

    async def extract_rules(self, transcript_text: str) -> List[Rule]:
        prompt = RULE_EXTRACTION_INSTRUCTIONS + "\n\nTranscript:\n" + transcript_text
        raw = await self._run_with_retry(prompt, RULES_SCHEMA)
        return self._validate_all(raw["rules"], Rule)

    async def extract_fields_from_transcript(
        self, transcript_text: str, existing_fields_context: Optional[str] = None
    ) -> List[FieldCandidate]:
        prompt = TRANSCRIPT_FIELD_EXTRACTION_INSTRUCTIONS + "\n\nTranscript:\n" + transcript_text
        if existing_fields_context:
            prompt += "\n\n" + EXISTING_FIELDS_CONTEXT_PREFIX + existing_fields_context + EXISTING_FIELDS_CONTEXT_SUFFIX
        raw = await self._run_with_retry(prompt, FIELDS_SCHEMA)
        return self._validate_all(raw["fields"], FieldCandidate)

    async def generate_stories(
        self, fields: List[FieldCandidate], rules: List[Rule], target_platform: str
    ) -> List[StoryItem]:
        fields_desc = "\n".join(
            f"- {f.name} ({f.field_type}{' → ' + f.lookup_target_entity if f.lookup_target_entity else ''}"
            f"{', required' if f.required else ''}"
            f"{', values: ' + ', '.join(f.choice_values) if f.choice_values else ''}) [{f.entity} / {f.section}]"
            for f in fields
        ) or "(none)"
        rules_desc = "\n".join(
            f"- [{r.source_detail}] ({r.rule_type}) {r.description}"
            + (f" — roles: {', '.join(r.roles_mentioned)}" if r.roles_mentioned else "")
            for r in rules
        ) or "(none)"
        prompt = (
            STORY_GENERATION_INSTRUCTIONS
            + f"\n\nTarget platform: {target_platform}\n\nDrafted fields:\n{fields_desc}"
            + f"\n\nExtracted rules:\n{rules_desc}"
        )
        raw = await self._run_with_retry(prompt, STORIES_SCHEMA)
        return self._validate_all(raw["stories"], StoryItem)

    async def generate_rbp_matrix(
        self,
        fields: List[FieldCandidate],
        rules: List[Rule],
        stories: List[StoryItem],
        target_platform: str,
        existing_grants_context: Optional[str] = None,
    ) -> List[RbpEntry]:
        fields_desc = "\n".join(f"- {f.name} [{f.entity}]" for f in fields) or "(none)"
        rules_desc = "\n".join(
            f"- [{r.source_detail}] {r.description}"
            + (f" — roles: {', '.join(r.roles_mentioned)}" if r.roles_mentioned else "")
            for r in rules
        ) or "(none)"
        stories_desc = "\n".join(f"- {s.story}" for s in stories) or "(none)"
        prompt = (
            RBP_GENERATION_INSTRUCTIONS
            + f"\n\nTarget platform: {target_platform}\n\nEntities/fields:\n{fields_desc}"
            + f"\n\nRules:\n{rules_desc}\n\nStories:\n{stories_desc}"
        )
        if existing_grants_context:
            prompt += "\n\n" + EXISTING_RBP_CONTEXT_PREFIX + existing_grants_context + EXISTING_RBP_CONTEXT_SUFFIX

        raw = await self._run_with_retry(prompt, RBP_SCHEMA)
        return self._validate_all(raw["entries"], RbpEntry)

    async def generate_process_flow(self, transcript_text: str, target_platform: str) -> ProcessFlow:
        prompt = (
            PROCESS_FLOW_GENERATION_INSTRUCTIONS
            + f"\n\nTarget platform: {target_platform}\n\nTranscript:\n{transcript_text}"
        )
        raw = await self._run_with_retry(prompt, PROCESS_FLOW_SCHEMA)
        steps = self._validate_all(raw["steps"], ProcessStep)
        transitions = self._validate_all(raw["transitions"], ProcessTransition)
        return ProcessFlow(steps=steps, transitions=transitions)

    async def _run_with_retry(self, prompt: str, schema: dict) -> dict:
        result = await self._invoke(prompt, schema)
        if result is not None:
            return result

        result = await self._invoke(prompt + STRICTER_RETRY_SUFFIX, schema)
        if result is not None:
            return result

        raise SchemaValidationError(
            "claude -p did not return a schema-valid result after one retry "
            "with a stricter formatting instruction."
        )

    async def _invoke(self, prompt: str, schema: dict) -> Optional[dict]:
        # Uploaded files live under data/uploads/, outside the CLI's default
        # trusted directory (its cwd) — without this, a screenshot read
        # silently fails permission and the model answers with an empty
        # result instead of an error.
        argv = [
            "claude", "-p", prompt,
            "--output-format", "json",
            "--json-schema", json.dumps(schema),
            "--add-dir", str(UPLOAD_DIR),
        ]
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
        except FileNotFoundError as exc:
            raise ClaudeSessionExpiredError(
                "The `claude` CLI isn't installed or isn't on PATH."
            ) from exc

        stderr_text = stderr.decode("utf-8", errors="replace")
        if process.returncode != 0:
            if self._looks_like_expired_session(stderr_text):
                raise ClaudeSessionExpiredError(
                    "Your Claude Code session has expired — run `claude /login` again."
                )
            return None

        try:
            envelope = json.loads(stdout.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return None

        if envelope.get("is_error") or envelope.get("subtype") != "success":
            error_text = str(envelope.get("result", ""))
            if self._looks_like_expired_session(error_text):
                raise ClaudeSessionExpiredError(
                    "Your Claude Code session has expired — run `claude /login` again."
                )
            return None

        return envelope.get("structured_output")

    @staticmethod
    def _looks_like_expired_session(text: str) -> bool:
        lowered = text.lower()
        return any(
            phrase in lowered
            for phrase in ("not logged in", "session has expired", "please log in", "/login", "authentication")
        )

    @staticmethod
    def _validate_all(raw_items: list, model: Type[T]) -> List[T]:
        items = []
        for raw in raw_items:
            try:
                items.append(model(**raw))
            except ValidationError as exc:
                raise SchemaValidationError(str(exc)) from exc
        return items
