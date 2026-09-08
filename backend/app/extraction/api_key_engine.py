import base64
import mimetypes
from pathlib import Path
from typing import List, Optional, Type, TypeVar

from anthropic import AsyncAnthropic
from pydantic import BaseModel, ValidationError

from ..config import load_config
from .base import ExtractionEngine
from .errors import SchemaValidationError
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
    FIELDS_TOOL,
    PROCESS_FLOW_TOOL,
    RBP_TOOL,
    RULES_TOOL,
    STORIES_TOOL,
    FieldCandidate,
    ProcessFlow,
    ProcessStep,
    ProcessTransition,
    RbpEntry,
    Rule,
    StoryItem,
)

MODEL = "claude-opus-5"

T = TypeVar("T", bound=BaseModel)


class APIKeyEngine(ExtractionEngine):
    """Anthropic Console API key, tool-use with a forced schema (technical spec §5).

    Structured output is guaranteed by the API: the tool is `strict` and
    `tool_choice` forces Claude to call it, so `tool_use.input` always
    matches the declared JSON Schema.
    """

    def __init__(self, api_key: Optional[str] = None):
        key = api_key or load_config().get("anthropic_api_key")
        if not key:
            raise RuntimeError(
                "No Anthropic API key configured. Set anthropic_api_key in "
                "config/config.json (see config/config.example.json)."
            )
        self._client = AsyncAnthropic(api_key=key)

    async def extract_fields(
        self,
        screenshot_path: str,
        transcript_context: Optional[str] = None,
        existing_fields_context: Optional[str] = None,
    ) -> List[FieldCandidate]:
        path = Path(screenshot_path)
        media_type = mimetypes.guess_type(path.name)[0] or "image/png"
        image_data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")

        text = FIELD_EXTRACTION_INSTRUCTIONS
        if transcript_context:
            text += "\n\n" + TRANSCRIPT_CONTEXT_PREFIX + transcript_context
        if existing_fields_context:
            text += "\n\n" + EXISTING_FIELDS_CONTEXT_PREFIX + existing_fields_context + EXISTING_FIELDS_CONTEXT_SUFFIX

        response = await self._client.messages.create(
            model=MODEL,
            max_tokens=4096,
            tools=[FIELDS_TOOL],
            tool_choice={"type": "tool", "name": "record_field_candidates"},
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": image_data},
                    },
                    {"type": "text", "text": text},
                ],
            }],
        )
        raw_fields = self._tool_input(response, "record_field_candidates")["fields"]
        return self._validate_all(raw_fields, FieldCandidate)

    async def extract_rules(self, transcript_text: str) -> List[Rule]:
        response = await self._client.messages.create(
            model=MODEL,
            max_tokens=4096,
            tools=[RULES_TOOL],
            tool_choice={"type": "tool", "name": "record_rules"},
            messages=[{
                "role": "user",
                "content": RULE_EXTRACTION_INSTRUCTIONS + "\n\nTranscript:\n" + transcript_text,
            }],
        )
        raw_rules = self._tool_input(response, "record_rules")["rules"]
        return self._validate_all(raw_rules, Rule)

    async def extract_fields_from_transcript(
        self, transcript_text: str, existing_fields_context: Optional[str] = None
    ) -> List[FieldCandidate]:
        text = TRANSCRIPT_FIELD_EXTRACTION_INSTRUCTIONS + "\n\nTranscript:\n" + transcript_text
        if existing_fields_context:
            text += "\n\n" + EXISTING_FIELDS_CONTEXT_PREFIX + existing_fields_context + EXISTING_FIELDS_CONTEXT_SUFFIX

        response = await self._client.messages.create(
            model=MODEL,
            max_tokens=4096,
            tools=[FIELDS_TOOL],
            tool_choice={"type": "tool", "name": "record_field_candidates"},
            messages=[{
                "role": "user",
                "content": text,
            }],
        )
        raw_fields = self._tool_input(response, "record_field_candidates")["fields"]
        return self._validate_all(raw_fields, FieldCandidate)

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
        text = (
            STORY_GENERATION_INSTRUCTIONS
            + f"\n\nTarget platform: {target_platform}\n\nDrafted fields:\n{fields_desc}"
            + f"\n\nExtracted rules:\n{rules_desc}"
        )

        response = await self._client.messages.create(
            model=MODEL,
            max_tokens=4096,
            tools=[STORIES_TOOL],
            tool_choice={"type": "tool", "name": "record_stories"},
            messages=[{"role": "user", "content": text}],
        )
        raw_stories = self._tool_input(response, "record_stories")["stories"]
        return self._validate_all(raw_stories, StoryItem)

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
        text = (
            RBP_GENERATION_INSTRUCTIONS
            + f"\n\nTarget platform: {target_platform}\n\nEntities/fields:\n{fields_desc}"
            + f"\n\nRules:\n{rules_desc}\n\nStories:\n{stories_desc}"
        )
        if existing_grants_context:
            text += "\n\n" + EXISTING_RBP_CONTEXT_PREFIX + existing_grants_context + EXISTING_RBP_CONTEXT_SUFFIX

        response = await self._client.messages.create(
            model=MODEL,
            max_tokens=4096,
            tools=[RBP_TOOL],
            tool_choice={"type": "tool", "name": "record_rbp_entries"},
            messages=[{"role": "user", "content": text}],
        )
        raw_entries = self._tool_input(response, "record_rbp_entries")["entries"]
        return self._validate_all(raw_entries, RbpEntry)

    async def generate_process_flow(self, transcript_text: str, target_platform: str) -> ProcessFlow:
        text = (
            PROCESS_FLOW_GENERATION_INSTRUCTIONS
            + f"\n\nTarget platform: {target_platform}\n\nTranscript:\n{transcript_text}"
        )
        response = await self._client.messages.create(
            model=MODEL,
            max_tokens=4096,
            tools=[PROCESS_FLOW_TOOL],
            tool_choice={"type": "tool", "name": "record_process_flow"},
            messages=[{"role": "user", "content": text}],
        )
        raw = self._tool_input(response, "record_process_flow")
        steps = self._validate_all(raw["steps"], ProcessStep)
        transitions = self._validate_all(raw["transitions"], ProcessTransition)
        return ProcessFlow(steps=steps, transitions=transitions)

    @staticmethod
    def _tool_input(response, tool_name: str) -> dict:
        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                return block.input
        raise SchemaValidationError(f"Claude did not call the {tool_name} tool.")

    @staticmethod
    def _validate_all(raw_items: list, model: Type[T]) -> List[T]:
        items = []
        for raw in raw_items:
            try:
                items.append(model(**raw))
            except ValidationError as exc:
                raise SchemaValidationError(str(exc)) from exc
        return items
