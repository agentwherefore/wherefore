from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

FieldType = Literal[
    "text", "phone", "email", "number", "date", "boolean",
    "choice", "lookup", "lookup_user",
]

LOOKUP_TYPES = {"lookup", "lookup_user"}

ReviewReason = Literal[
    "ambiguous_entity", "ambiguous_form", "low_confidence", "missing_lookup_target",
    "missing_supporting_field", "missing_choice_values", "missing_acceptance_criteria",
]
RuleType = Literal["business_rule", "exception", "role_mention"]


class FieldCandidate(BaseModel):
    name: str
    field_type: FieldType
    required: bool
    entity: str
    section: str
    # Required (non-null) when field_type is "lookup" or "lookup_user" — the
    # entity/table this field points to (e.g. "Call Reason", "User"). A
    # "Lookup" with no named target isn't buildable, so this is not optional
    # metadata — the pipeline also uses it to make sure the target entity
    # itself shows up in the Field Listing (see extraction/pipeline.py).
    lookup_target_entity: Optional[str] = None
    # Required (non-empty) when field_type is "choice" — the actual values a
    # developer would configure as the option set (e.g. ["New", "Assigned",
    # "In Progress", "Closed", "Escalated"]). Null for every other type.
    choice_values: Optional[List[str]] = None
    # True for at most one field per entity — the field that identifies a
    # record of that entity to a human (usually a Name-like text field).
    # Every entity a Lookup points to needs exactly one of these to be
    # useful in a lookup search; not every entity necessarily has one (e.g.
    # a platform-auto-numbered record has no human-entered name field) —
    # leaving every field on an entity false is valid when there's no clear
    # candidate, and is preferred over guessing wrong.
    is_primary_field: bool = False
    source_detail: str
    status: Literal["approved", "needs_review"] = "approved"
    review_reason: Optional[ReviewReason] = None
    rationale: str

    @model_validator(mode="after")
    def _flag_missing_lookup_target(self) -> "FieldCandidate":
        if self.field_type in LOOKUP_TYPES and not self.lookup_target_entity:
            self.status = "needs_review"
            self.review_reason = "missing_lookup_target"
        elif self.field_type == "choice" and not self.choice_values:
            self.status = "needs_review"
            self.review_reason = "missing_choice_values"
        return self


class Rule(BaseModel):
    description: str
    rule_type: RuleType
    source_detail: str
    roles_mentioned: List[str] = Field(default_factory=list)
    status: Literal["approved", "needs_review"] = "approved"
    review_reason: Optional[ReviewReason] = None


class StoryItem(BaseModel):
    epic: str
    feature: str
    story: str
    # Multiple Given/When/Then criteria per story — happy path plus whatever
    # edge/validation cases the source rules actually support — not a single
    # condition standing in for the whole story.
    acceptance_criteria: List[str]
    source_detail: str
    status: Literal["approved", "needs_review"] = "approved"
    review_reason: Optional[ReviewReason] = None

    @model_validator(mode="after")
    def _flag_missing_acceptance_criteria(self) -> "StoryItem":
        if not self.acceptance_criteria:
            self.status = "needs_review"
            self.review_reason = "missing_acceptance_criteria"
        return self


class RbpEntry(BaseModel):
    role: str
    entity: str
    can_create: bool
    can_read: bool
    read_scope: Optional[str] = None  # e.g. "own records only"; null if unrestricted or can_read is false
    can_update: bool
    can_delete: bool
    can_reassign: bool
    source_detail: str
    status: Literal["approved", "needs_review"] = "approved"
    review_reason: Optional[ReviewReason] = None


StepType = Literal["start", "task", "decision", "end"]


class ProcessStep(BaseModel):
    # Stable identifier invented by the model, used only to reference this
    # step from a ProcessTransition — not shown to the user directly.
    step_key: str
    label: str
    actor: str  # role performing this step, or "System" if automated
    step_type: StepType
    source_detail: str
    status: Literal["approved", "needs_review"] = "approved"
    review_reason: Optional[ReviewReason] = None


class ProcessTransition(BaseModel):
    from_step: str  # a ProcessStep.step_key
    to_step: str  # a ProcessStep.step_key
    condition: Optional[str] = None  # e.g. "Inspection passes"; null if unconditional


class ProcessFlow(BaseModel):
    steps: List[ProcessStep]
    transitions: List[ProcessTransition]


# Hand-written JSON Schemas shared by both engines: APIKeyEngine uses them as
# an Anthropic tool's forced input_schema; ClaudeCodeCLIEngine passes them to
# `claude -p --json-schema`. Strict/CLI schema validation requires every
# property to be listed in `required` (optional fields are nullable rather
# than omitted) — Pydantic above is still the source of truth for the actual
# validation both engines run on the result.

FIELD_CANDIDATE_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "field_type": {"type": "string", "enum": list(FieldType.__args__)},
        "required": {"type": "boolean"},
        "entity": {"type": "string"},
        "section": {"type": "string"},
        "lookup_target_entity": {"type": ["string", "null"]},
        "choice_values": {"type": ["array", "null"], "items": {"type": "string"}},
        "is_primary_field": {"type": "boolean"},
        "source_detail": {"type": "string"},
        "status": {"type": "string", "enum": ["approved", "needs_review"]},
        "review_reason": {
            "type": ["string", "null"],
            "enum": list(ReviewReason.__args__) + [None],
        },
        "rationale": {"type": "string"},
    },
    "required": [
        "name", "field_type", "required", "entity", "section",
        "lookup_target_entity", "choice_values", "is_primary_field",
        "source_detail", "status", "review_reason", "rationale",
    ],
    "additionalProperties": False,
}

RULE_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "rule_type": {"type": "string", "enum": list(RuleType.__args__)},
        "source_detail": {"type": "string"},
        "roles_mentioned": {"type": "array", "items": {"type": "string"}},
        "status": {"type": "string", "enum": ["approved", "needs_review"]},
        "review_reason": {
            "type": ["string", "null"],
            "enum": list(ReviewReason.__args__) + [None],
        },
    },
    "required": [
        "description", "rule_type", "source_detail", "roles_mentioned",
        "status", "review_reason",
    ],
    "additionalProperties": False,
}

FIELDS_SCHEMA = {
    "type": "object",
    "properties": {"fields": {"type": "array", "items": FIELD_CANDIDATE_ITEM_SCHEMA}},
    "required": ["fields"],
    "additionalProperties": False,
}

RULES_SCHEMA = {
    "type": "object",
    "properties": {"rules": {"type": "array", "items": RULE_ITEM_SCHEMA}},
    "required": ["rules"],
    "additionalProperties": False,
}

STORY_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "epic": {"type": "string"},
        "feature": {"type": "string"},
        "story": {"type": "string"},
        "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
        "source_detail": {"type": "string"},
        "status": {"type": "string", "enum": ["approved", "needs_review"]},
        "review_reason": {
            "type": ["string", "null"],
            "enum": list(ReviewReason.__args__) + [None],
        },
    },
    "required": [
        "epic", "feature", "story", "acceptance_criteria",
        "source_detail", "status", "review_reason",
    ],
    "additionalProperties": False,
}

STORIES_SCHEMA = {
    "type": "object",
    "properties": {"stories": {"type": "array", "items": STORY_ITEM_SCHEMA}},
    "required": ["stories"],
    "additionalProperties": False,
}

RBP_ENTRY_SCHEMA = {
    "type": "object",
    "properties": {
        "role": {"type": "string"},
        "entity": {"type": "string"},
        "can_create": {"type": "boolean"},
        "can_read": {"type": "boolean"},
        "read_scope": {"type": ["string", "null"]},
        "can_update": {"type": "boolean"},
        "can_delete": {"type": "boolean"},
        "can_reassign": {"type": "boolean"},
        "source_detail": {"type": "string"},
        "status": {"type": "string", "enum": ["approved", "needs_review"]},
        "review_reason": {
            "type": ["string", "null"],
            "enum": list(ReviewReason.__args__) + [None],
        },
    },
    "required": [
        "role", "entity", "can_create", "can_read", "read_scope", "can_update",
        "can_delete", "can_reassign", "source_detail", "status", "review_reason",
    ],
    "additionalProperties": False,
}

RBP_SCHEMA = {
    "type": "object",
    "properties": {"entries": {"type": "array", "items": RBP_ENTRY_SCHEMA}},
    "required": ["entries"],
    "additionalProperties": False,
}

PROCESS_STEP_SCHEMA = {
    "type": "object",
    "properties": {
        "step_key": {"type": "string"},
        "label": {"type": "string"},
        "actor": {"type": "string"},
        "step_type": {"type": "string", "enum": list(StepType.__args__)},
        "source_detail": {"type": "string"},
        "status": {"type": "string", "enum": ["approved", "needs_review"]},
        "review_reason": {
            "type": ["string", "null"],
            "enum": list(ReviewReason.__args__) + [None],
        },
    },
    "required": [
        "step_key", "label", "actor", "step_type", "source_detail", "status", "review_reason",
    ],
    "additionalProperties": False,
}

PROCESS_TRANSITION_SCHEMA = {
    "type": "object",
    "properties": {
        "from_step": {"type": "string"},
        "to_step": {"type": "string"},
        "condition": {"type": ["string", "null"]},
    },
    "required": ["from_step", "to_step", "condition"],
    "additionalProperties": False,
}

PROCESS_FLOW_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {"type": "array", "items": PROCESS_STEP_SCHEMA},
        "transitions": {"type": "array", "items": PROCESS_TRANSITION_SCHEMA},
    },
    "required": ["steps", "transitions"],
    "additionalProperties": False,
}

FIELDS_TOOL = {
    "name": "record_field_candidates",
    "description": "Record every field candidate detected in the screenshot.",
    "strict": True,
    "input_schema": FIELDS_SCHEMA,
}

RULES_TOOL = {
    "name": "record_rules",
    "description": "Record every business rule, exception, or role mention detected in the transcript.",
    "strict": True,
    "input_schema": RULES_SCHEMA,
}

STORIES_TOOL = {
    "name": "record_stories",
    "description": "Record the Epic → Feature → Story → Acceptance Criteria tree built from the drafted fields and extracted rules.",
    "strict": True,
    "input_schema": STORIES_SCHEMA,
}

RBP_TOOL = {
    "name": "record_rbp_entries",
    "description": "Record the Role-Based Permissions matrix — which role can Create/Read/Update/Delete/Reassign which entity.",
    "strict": True,
    "input_schema": RBP_SCHEMA,
}

PROCESS_FLOW_TOOL = {
    "name": "record_process_flow",
    "description": "Record the current (as-is) process flow described in the transcript, as a sequence of steps and transitions.",
    "strict": True,
    "input_schema": PROCESS_FLOW_SCHEMA,
}
