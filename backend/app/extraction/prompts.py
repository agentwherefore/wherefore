# Shared between both engines so their behavior stays comparable — only the
# schema-enforcement mechanism differs (forced tool-use vs. --json-schema).

# A "Lookup" with no named target isn't buildable — a developer needs to
# know which entity/table it points to, and that entity needs to actually
# appear in the Field Listing too, not just be implied. Spliced into both
# field-extraction prompts below so the requirement holds regardless of
# which source (screenshot or transcript) produced the lookup field.
LOOKUP_TARGET_INSTRUCTIONS = """
Every "lookup" or "lookup_user" field must name what it points to, via lookup_target_entity: the entity/table this field looks up to (e.g. "Call Reason", "User"). Never leave a lookup field without a named target. For "lookup_user", the target is the platform's user/staff entity — use "User". For a generic "lookup", use the specific entity name implied by what the values represent (e.g. a Call Reason lookup targets a "Call Reason" entity, not "Case").

If that target entity is not itself one of the entities you're already recording fields for elsewhere in this same batch, you must ALSO emit a separate field candidate for that target entity's own primary field, so it actually shows up in the Field Listing instead of being an unbuilt reference: name "Name", field_type "text", required true, is_primary_field true, entity set to the same lookup_target_entity, section "<that entity> Details", lookup_target_entity null, choice_values null, and a rationale explaining it was added to support the lookup. Do this once per missing target entity, not once per field that references it."""

# Spliced into both field-extraction prompts, same reasoning as
# LOOKUP_TARGET_INSTRUCTIONS above: a Field Listing that doesn't say which
# field identifies a record, or what a Choice field's actual values are,
# isn't buildable either.
FIELD_QUALITY_INSTRUCTIONS = """
- is_primary_field: true for at most one field per entity — the field that best identifies a record of that entity to a human (usually a Name-like text field, e.g. "Facility Name" for Facility, "Caller Name" for Contact). If an entity clearly has no obvious identifying field (e.g. it's expected to be auto-numbered by the platform), leave every field on that entity is_primary_field false rather than guessing — never mark two fields on the same entity as primary.
- choice_values: required (a non-empty list) whenever field_type is "choice" — the actual option values, exactly as shown or described (e.g. ["New", "Assigned", "In Progress", "Closed", "Escalated"]). Null for every other field_type. If you cannot determine the actual values, do not invent plausible-sounding ones — leave choice_values empty and set status "needs_review" with review_reason "missing_choice_values"."""

FIELD_EXTRACTION_INSTRUCTIONS = """You are extracting field candidates from a screenshot of a business application form, for a functional consultant building a Field Listing during discovery.

For every input field you can see in the screenshot, record:
- name: the field's label as shown.
- field_type: one of text, phone, email, number, date, boolean, choice, lookup, lookup_user — infer from the input control and any sample values shown. A dropdown of values that could plausibly change over time (not a small fixed set the business will never touch) should be "lookup", not "choice". A dropdown of staff/user names should be "lookup_user".
- required: true if the screenshot shows an explicit required-field indicator (e.g. an asterisk), OR if it's a core identifying/load-bearing field a record of this type cannot meaningfully exist without (e.g. a person's name on a Contact-type entity, the primary identifying field of any entity). Do not let "no visible indicator" alone decide required is false when the field is clearly essential — most fields on a real form are required in practice. If you're genuinely unsure, set required to false but flag status "needs_review" with review_reason "low_confidence" rather than silently defaulting to not-required.
- entity: the target table/entity this field conceptually belongs to (e.g. "Case", "Contact"). Infer this from the screen's title/header and the kind of data being captured — personal/identity details usually belong on a Contact-type entity, transactional/case details on a Case-type entity, even if the screenshot doesn't say the word "entity" anywhere.
- section: the form or tab section the field appears under, taken from the screen's title/header.
- lookup_target_entity: see instructions below — required for lookup/lookup_user fields, null for every other field_type.
- source_detail: a short, specific citation of where in the screenshot you found it (e.g. "top-left of the form", "second column").
- status: "needs_review" if you are not confident about the field's type, its entity assignment, or whether this screen is the same form as another one you've already seen fields from; otherwise "approved".
- review_reason: required whenever status is "needs_review" — "ambiguous_entity" if the entity assignment is unclear, "ambiguous_form" if you cannot tell whether this screen is the same form as another you've seen (e.g. a differently-named header for what might be the same screen), or "low_confidence" for anything else. Must be null when status is "approved".
- rationale: one or two plain-language sentences a consultant could read in a trace panel, explaining why the field was typed and assigned the way it was.

Record every field you find. Do not skip fields, and do not invent fields you cannot see.
""" + LOOKUP_TARGET_INSTRUCTIONS + FIELD_QUALITY_INSTRUCTIONS + """

If a discovery call transcript is also provided below, use it to inform field_type, required, and status/review_reason — a field's correct type sometimes only becomes clear from what was said in the call, not from the screenshot alone. For example, a dropdown with no visible options in the screenshot is a "lookup", not a "choice", if the transcript says its values change over time or get added to without a deployment. When the transcript resolves what would otherwise be a low_confidence type guess, use the transcript to decide the type and set status to "approved" — do not leave it needs_review just because the screenshot alone was ambiguous."""

TRANSCRIPT_CONTEXT_PREFIX = "Discovery call transcript for this project (use it to inform field types and requirements, per the instructions above):\n"

EXISTING_FIELDS_CONTEXT_PREFIX = """Fields already recorded for this project from a previous session, grouped by entity:
"""

EXISTING_FIELDS_CONTEXT_SUFFIX = """
If you find a field that is the same as one of these, use the exact same name and entity — do not reclassify it under a different entity, and do not invent a rephrased name for it. Only include it in your output if you are correcting something previously flagged for review; otherwise, only record fields that are genuinely new and not in this list."""

TRANSCRIPT_FIELD_EXTRACTION_INSTRUCTIONS = """You are extracting field candidates directly from a discovery call transcript, for a functional consultant building a Field Listing — independent of any screenshot, based purely on what the transcript describes needing to be tracked.

For every distinct piece of data the conversation implies needs to be captured or stored (an attribute of some entity/table, e.g. "Facility Name," "Inspection Date," "Violation Code"), record:
- name: a concise field label, in the same style a form field would use (e.g. "Facility Name", not a full sentence).
- field_type: one of text, phone, email, number, date, boolean, choice, lookup, lookup_user — infer from how the data is described. A value set that can grow or change over time (new categories/codes added later without a deployment) should be "lookup", not "choice".
- required: true if the transcript explicitly says so, OR if the field is clearly essential for a record of this type to make sense (e.g. a Facility cannot exist without a Facility Name; an Inspection cannot exist without an Inspection Date) — most primary identifying and core operational fields are required in practice even when a discovery conversation never uses the word "required." Do not default to false just because it wasn't explicitly stated; reserve false for fields that are genuinely optional or supplementary (e.g. a free-text comments field). If you're unsure, set required to false but flag status "needs_review" with review_reason "low_confidence" rather than silently guessing.
- entity: the target table/entity this field belongs to (e.g. "Facility", "Inspection", "Complaint", "Violation"), inferred from context.
- section: a short grouping label for related fields on that entity (e.g. "Facility Details", "Inspection Result").
- lookup_target_entity: see instructions below — required for lookup/lookup_user fields, null for every other field_type.
- source_detail: the transcript timestamp where this was described, exactly as given.
- status: "needs_review" if the transcript only vaguely implies this field, or you had to infer specifics it didn't state; otherwise "approved".
- review_reason: required whenever status is "needs_review" (use "low_confidence" unless the ambiguity is specifically about entity/form assignment). Must be null when status is "approved".
- rationale: one or two plain-language sentences explaining why this field and type were inferred from the conversation.

Only record fields the transcript actually implies are needed — don't invent an exhaustive theoretical data model, and don't restate the same field twice under slightly different names. Business rules, exceptions, and role permissions belong to a separate extraction step — only record concrete data-capture fields here, not process rules or behavior.
""" + LOOKUP_TARGET_INSTRUCTIONS + FIELD_QUALITY_INSTRUCTIONS

STORY_GENERATION_INSTRUCTIONS = """You are turning drafted fields and extracted business rules into a Story Tree for a functional consultant, organized as Epic → Feature → Story → Acceptance Criteria.

Group related stories under a shared Feature, and related features under a shared Epic, based on the fields and rules given below. For every distinct piece of user-facing behavior implied by the rules (using the fields for grounding where relevant), record:
- epic: a short name for the overall capability area (e.g. "Case Intake Management").
- feature: a short name for the specific capability within that epic (e.g. "Case Assignment").
- story: a single user story in the form "As a <role>, I want <goal>, so that <benefit>." Use a role actually mentioned in the rules when possible; otherwise use a sensible generic role for this kind of system.
- acceptance_criteria: a LIST of testable conditions, each in Given/When/Then form, that a tester could execute directly against the system and get a pass/fail — not a single paraphrase of the rule standing in for the whole story. Where the source rule material supports it, cover the story from more than one angle:
  - the primary/happy-path case,
  - any exception, boundary, or "what if this ISN'T met" case the rules explicitly describe for this behavior,
  - a validation/negative case where the rules imply the system should prevent or reject something, not only allow it.
  Do not pad the list to hit a target count — a rule that only supports one genuine criterion should produce a list of one; do not invent a second or third scenario the source material doesn't actually describe. Use the exact field and entity names from the "Drafted fields" list below in every criterion; never invent a field name that isn't listed there. State exactly what system state is being checked (e.g. "the Case's Assigned To field is populated" rather than "the case is assigned"; "the Case's Status field equals Escalated" rather than "the case is escalated"). If verifying part of the rule as stated would require a field, timestamp, or automation that isn't in the drafted fields provided (e.g. an SLA due-date field to check a 15-minute time limit, or an audit-timestamp field to check "within 24 hours"), do not invent one — write the closest testable criterion the given fields actually support instead, and set status to "needs_review" with review_reason "missing_supporting_field".
- source_detail: the transcript timestamp of the rule this story is built from, exactly as given.
- status: "needs_review" if the story required inventing details the rules didn't actually state, if two rules seem to conflict, or if any acceptance criterion can't be fully verified with the fields given (see above); otherwise "approved".
- review_reason: required whenever status is "needs_review" — "missing_supporting_field" per above, "low_confidence" for other uncertainty, or the entity/form reasons if that's specifically the issue. Must be null when status is "approved".

Do not invent business rules that were not given to you — every story must trace back to a specific rule. It is fine to have only one story under a feature, and only one feature under an epic, if that's all the rules support."""

RBP_GENERATION_INSTRUCTIONS = """You are turning drafted fields, extracted rules, and generated user stories into a Role-Based Permissions (RBP) Matrix for a functional consultant — which role can Create/Read/Update/Delete/Reassign records of which entity.

For every role mentioned in the rules or stories below, and every entity it plausibly interacts with, record:
- role: the role name, exactly as used in the rules/stories (e.g. "Agent", "Supervisor") — do not invent a role that isn't mentioned there.
- entity: the entity this permission grant applies to (must be one of the entities in the fields provided).
- can_create / can_read / can_update / can_delete / can_reassign: booleans — true only if the rules/stories state or clearly imply this role has that capability on this entity. Default to false rather than guessing generously; an ungranted permission is safer than a wrongly-granted one.
- read_scope: if can_read is true and the source material implies a restriction (e.g. only their own records, not everyone's), state it in a few words (e.g. "own records only"). Null if unrestricted or can_read is false.
- source_detail: the transcript timestamp or rule this grant is based on.
- status: "needs_review" if you had to infer a permission the source material didn't explicitly state; otherwise "approved".
- review_reason: required whenever status is "needs_review" (use "low_confidence" unless it's specifically about entity assignment). Must be null when status is "approved".

Only record a role/entity pair if there is something to say about it — do not emit an all-false row for a role that was never discussed in relation to that entity. A role with only one capability (e.g. read-only) is fine if that's all the source material supports. Do not invent roles or entities that are not present in what you were given."""

EXISTING_RBP_CONTEXT_PREFIX = """Role/entity permission grants already recorded for this project from a previous session:
"""

EXISTING_RBP_CONTEXT_SUFFIX = """
If a role/entity pair above already has a grant recorded, do not record it again — only record a new role/entity pair, or one genuinely new capability for a role on an entity not already listed above."""

RULE_EXTRACTION_INSTRUCTIONS = """You are extracting business rules, exceptions, and role mentions from a discovery call transcript, for a functional consultant building a Story Tree and RBP Matrix.

For every distinct rule, exception, or role-related statement you find in the transcript, record:
- description: a plain-language statement of the rule (e.g. "Urgent or safety-flagged calls must be assigned within 15 minutes").
- rule_type: "business_rule" for a general rule, "exception" for a stated exception/edge case, or "role_mention" for a statement about what a role can or cannot do or see.
- source_detail: the transcript timestamp where this was said, exactly as shown (e.g. "04:12").
- roles_mentioned: any roles referenced by this rule (e.g. ["Agent", "Supervisor"]); empty list if none.
- status: "needs_review" if the statement is vague, contradicts an earlier statement, or you are not confident you've captured it correctly; otherwise "approved".
- review_reason: required whenever status is "needs_review" (use "low_confidence" unless the ambiguity is specifically about which entity/form it concerns, in which case use "ambiguous_entity" or "ambiguous_form"). Must be null when status is "approved".

Record every rule, exception, and role mention you find. Do not skip any, and do not invent rules that were not stated."""

PROCESS_FLOW_GENERATION_INSTRUCTIONS = """You are mapping the CURRENT (as-is) process flow described in a discovery call transcript, for a functional consultant documenting how the business operates today — not the future system being designed.

Read the transcript and reconstruct the sequence of steps as they happen today, as a flowchart: a list of steps and the transitions between them.

For every distinct step in the process, record:
- step_key: a short stable identifier you invent for this step (e.g. "step_1", "step_2") — used only to reference this step in transitions, never shown to the user directly.
- label: a short, plain-language description of what happens at this step (e.g. "Agent logs new call", "Supervisor reviews complaint").
- actor: who performs this step — a role mentioned in the transcript (e.g. "Agent", "Supervisor"). Use "System" if the step is automated with no human actor.
- step_type: "start" for the step that begins the process, "end" for a step that terminates it (there can be more than one end — e.g. different outcomes), "decision" for a branch point where the next step depends on a condition, "task" for everything else.
- source_detail: the transcript timestamp this step is drawn from.
- status: "needs_review" if the transcript only vaguely implies this step or its position in the sequence; otherwise "approved".
- review_reason: required whenever status is "needs_review" (use "low_confidence" unless it's specifically about which entity/form the step concerns). Must be null when status is "approved".

For every transition between two steps, record:
- from_step / to_step: the step_key values of the two steps this transition connects.
- condition: if this transition only happens under a specific condition (typically coming out of a decision step), state it in a few words (e.g. "Inspection passes", "Urgent flag set"). Null for an unconditional transition.

Only map what the transcript actually describes — do not invent steps or reorder based on assumption. If the transcript describes multiple distinct processes (e.g. intake and, separately, enforcement), include all of them; they don't need to connect into a single unbroken chain if the transcript doesn't connect them. A small number of steps is fine if that's all the transcript supports."""
