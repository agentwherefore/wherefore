# Wherefore — Technical Specification

**Audience:** implementer (you, in Claude Code). Architecture, stack, data
model, and build sequencing. Assumes the product context in
`functional-spec.md` — this document focuses on how it's built,
not what it does or why.

---

## 1. Architecture: Core + Adapters

- **Core (platform-agnostic):** intake handling, extraction reasoning,
  story/test generation, traceability engine, process flow generation.
- **D365 adapter (V1's only platform adapter):** Dataverse field-type
  vocabulary, D365 security-role model.
- **ADO adapter** (destination-tool axis, separate from platform): backlog
  push — Phase 2.
- **Salesforce adapter:** designed for via the adapter pattern, not built.

Broadening later means adding an adapter, not rebuilding the core.

## 2. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Backend | FastAPI (Python) | Matches existing Python fluency |
| Database | SQLite | Single-operator tool; no client-server DB needed |
| Access control | None — localhost-only, single operator | Rest of the stack doesn't support multi-tenancy; see §6 |
| Claude access | Dual adapter — see §5 | — |
| Frontend | Existing HTML/CSS/JS prototype, wired to the real backend progressively | Reach for a framework only if state management demands it |
| File storage | Local filesystem | No cloud storage needed for single-operator use |

## 3. System Access & Configuration

- TR-1 App binds to localhost only; no accounts, no login screen.
- TR-2 Claude access mode is a single setting in a local config file, not a
  per-user database record (there is no `users` table — see §4).
- TR-3 If ever run somewhere reachable beyond localhost: a single
  shared-secret check in middleware — deferred, not built now (§8).
- TR-4 API key, if used, stored in a local config file excluded from git via
  `.gitignore` — never committed, never logged.

## 4. Data Model

```
projects             id, name, target_platform (d365 | salesforce),
                      status (draft | in_review | pushed), created_at, updated_at

uploaded_files        id, project_id, type (transcript | screenshot |
                      video_recording), filename, storage_path, uploaded_at,
                      processed_at (nullable — set once this file has
                      contributed to a draft generation run; lets a
                      follow-up "Update Draft" pass process only newly-added
                      files instead of re-running extraction on everything)
                      -- video_recording is stored and playable only; not
                      -- yet auto-transcribed (audio transcription remains
                      -- deferred, see §8)

field_listing_items   id, project_id, name, field_type, required (bool),
                      entity (target table, e.g. "Case" | "Contact"),
                      section (form/tab section within that entity),
                      lookup_target_entity (nullable; required in practice
                      when field_type is lookup/lookup_user — the entity
                      this field points to, e.g. "Call Reason", "User"),
                      choice_values (JSON array, nullable; required in
                      practice when field_type is choice — actual option
                      values, e.g. ["New","Assigned","Closed"]),
                      is_primary_field (bool; true for at most one field
                      per entity — the field that identifies a record to a
                      human, e.g. "Facility Name" for Facility),
                      source_type (transcript | screenshot | consultant_note |
                      screenshot+transcript -- when the same field was found
                      via both, deduped into one row citing both),
                      source_file_id (FK -> uploaded_files, nullable --
                      the screenshot's id when source_type is combined),
                      source_detail (e.g. "04:12", "Column G", "row 14"),
                      status (approved | needs_review),
                      review_reason (e.g. "ambiguous_entity", "ambiguous_form",
                      "low_confidence" -- set when status is needs_review),
                      created_at

story_tree_items      id, project_id, epic, feature, story,
                      acceptance_criteria, source_ref

rbp_matrix_items      id, project_id, role, entity, can_create, can_read,
                      read_scope (nullable, e.g. "own records only"),
                      can_update, can_delete, can_reassign,
                      source_file_id (FK -> uploaded_files, nullable),
                      source_detail, status (approved | needs_review),
                      review_reason -- pulled forward from Phase 2, see §5

process_flow_steps    id, project_id, step_key (stable within a project,
                      referenced only by process_flow_transitions, never
                      shown directly), label, actor (role or "System"),
                      step_type (start | task | decision | end),
                      source_file_id (FK -> uploaded_files, nullable),
                      source_detail, status (approved | needs_review),
                      review_reason, created_at

process_flow_transitions  id, project_id, from_step_key, to_step_key,
                      condition (nullable -- e.g. "Inspection passes";
                      null for an unconditional transition), created_at

consultant_notes      id, project_id, note_text, related_field_id (nullable),
                      source ('chat'), created_at
```

No `users` table in V1. If extended to real multi-user use later: add
`users` and a `user_id` FK on `projects`. Every other table already hangs
off `project_id`, so that extension doesn't touch the rest of the schema.

## 5. Claude Access Engine Design

Single interface, two implementations, selected by `TR-2`'s config setting:

```
ExtractionEngine
  extract_fields(screenshot, transcript_context=None) → List[FieldCandidate]
  extract_fields_from_transcript(transcript)          → List[FieldCandidate]
  extract_rules(transcript)                           → List[Rule]
  generate_stories(fields, rules, target_platform)    → List[StoryItem]
  generate_rbp_matrix(fields, rules, stories,
    target_platform, existing_grants_context=None)    → List[RbpEntry]
  generate_process_flow(transcript_text,
    target_platform)                                   → ProcessFlow
```

`extract_fields_from_transcript` was added once a real transcript-only
project (no screenshots at all — a brand-new system discussed purely in
conversation, no legacy UI to screenshot) came back with a populated Story
Tree but an empty Field Listing: field extraction was screenshot-only, so a
transcript rich with implied data requirements (Facility, Inspection,
Violation, ...) produced zero fields. The pipeline now runs both sources
and merges the results, deduping by `(entity, name)` case-insensitively —
a field named in both a screenshot and the transcript becomes one row with
a combined `source_type` (e.g. `screenshot+transcript`) and a source_detail
citing both, not two separate rows. When both exist, the screenshot's
typing wins (it's the more directly observed source).

`transcript_context` was added after the first implementation surfaced a real
gap: a field's correct type sometimes only resolves once the screenshot is
read alongside the transcript — e.g. Call Reason's dropdown shows no values
in the screenshot, so it reads as a plain Choice in isolation; it only
becomes a Lookup once the transcript's "categories change every quarter"
line is available in the same call. `extract_fields` accepts the project's
transcript text (when one has been uploaded) precisely so this kind of
cross-referencing happens inside a single model call, rather than requiring
a separate reconciliation pass across independently-drafted fields and
rules. This does not extend to cross-referencing between multiple
screenshots (e.g. catching two differently-named forms that turn out to be
the same screen) — each screenshot is still extracted independently.

**Incremental updates (FR-12a).** `DraftGenerationSession` (in
`extraction/pipeline.py`) only ever runs extraction against
previously-unprocessed uploads (`uploaded_files.processed_at IS NULL`) and
only ever inserts new `field_listing_items`/`story_tree_items` rows — it
never deletes or updates an existing one. Rules and transcript-sourced
fields are extracted from new transcript text only (not the full history)
so a follow-up run doesn't re-derive — and re-story — rules already turned
into stories in an earlier run; full transcript history is still passed as
*context* to new-screenshot field typing, since that's free (no LLM call)
and can resolve ambiguity from an earlier meeting. New field candidates are
deduped against already-persisted fields by `(entity, name)`
case-insensitively before insert — a field named again in new material is
skipped, not duplicated. Known limitation: if an early screenshot's field
was drafted `needs_review` before a later meeting's transcript would have
resolved it, that field is not retroactively re-typed — only genuinely new
files trigger new extraction, so an already-drafted item stays as reviewed
by a human, consistent with the "nothing changes without approval" rule.

**Lookup targets (FR-7b).** `FieldCandidate.lookup_target_entity` is
required by both field-extraction prompts whenever `field_type` is
`lookup`/`lookup_user` — a `model_validator` self-heals a model slip (empty
target on a lookup type) into `status: needs_review`,
`review_reason: missing_lookup_target` rather than raising, so one bad item
doesn't fail the whole run. Both prompts also instruct the model to emit a
second field candidate — the target entity's own primary field (`name:
"Name"`) — whenever that target isn't already one of the entities being
recorded in the same batch, so a Lookup's target entity actually appears in
the Field Listing instead of being an unbuilt reference. This is
prompt-enforced, not code-enforced — the pipeline doesn't independently
verify a target entity got synthesized; a needs_review flag is the
backstop when the model doesn't comply.

**Required, primary field, choice values (FR-7c/7d/7e).** All three were
missing or systematically wrong when checked against real projects: the
`required` instruction only allowed `true` on explicit evidence (an
asterisk, an explicit "mandatory" statement), which almost never fires for
`extract_fields_from_transcript` since a discovery conversation rarely
states requiredness explicitly — one project came back with 0/41 fields
required, another 2/70. Broadened to also allow `true` when a field is
obviously load-bearing for the record to exist (a person's name on
Contact, a Facility's own name), with `needs_review`/`low_confidence` as
the fallback for genuine uncertainty instead of a silent `false`. Primary
field and choice values didn't exist as fields at all — a Choice field's
actual option values were sometimes present in the model's `rationale`
prose but never captured as structured data the UI could display, and
nothing marked which field identifies a record of an entity (needed for
any Lookup pointing at it to be meaningful in a lookup search). Both added
to `FieldCandidate`; `is_primary_field` gets a deterministic cross-call and
cross-run backstop in `pipeline.py` (`dedupe_primary`) — the model is only
prompted not to double-mark an entity's primary field, but a second claim
is forced to `false` regardless, since screenshot- and transcript-derived
extraction are separate calls with no shared memory otherwise.

**Testable acceptance criteria (FR-11).** The first version of
`STORY_GENERATION_INSTRUCTIONS` only asked for "a specific, testable
condition," which produced paraphrases of the rule (e.g. "the case must be
assigned within 15 minutes") rather than something a tester could actually
execute against the system — no named field, no checkable system state.
Acceptance criteria are now required in Given/When/Then form, referencing
the exact field/entity names from the drafted fields list (never an
invented name), stating precisely what system state is checked (e.g. "the
Case's Assigned To field is populated," not "the case is assigned"). Some
rules imply a mechanism the drafted fields don't yet support — a 15-minute
SLA needs a due-date or timestamp field to actually verify, which the
canonical fixture's Field Listing has no field for. Rather than invent one,
the model writes the closest criterion the given fields support and flags
`status: needs_review`, `review_reason: missing_supporting_field` — a
distinct reason from `low_confidence`, so a consultant can tell "the model
wasn't sure" apart from "this genuinely needs a new field before it's
verifiable."

**Multiple acceptance criteria per story (FR-11c).** `acceptance_criteria`
was originally a single string — one Given/When/Then condition standing in
for the whole story, even when the source rules clearly described more
than one testable angle on it (a happy path, plus an explicit exception or
a validation case the transcript separately stated, e.g. "a case can't be
closed while unassigned"). Changed to `List[str]` on `StoryItem`
(`schemas.py`) and `Column(JSON)` on `StoryTreeItem` (`models.py`, same
pattern as `FieldCandidate.choice_values`). `STORY_GENERATION_INSTRUCTIONS`
now asks for 1+ criteria covering the happy path plus whatever
exception/boundary/validation case the rules actually support — explicitly
told not to pad the list to hit a target count, since an invented second
scenario is worse than a single well-grounded one. A `model_validator`
mirrors the `FieldCandidate` pattern: an empty list is self-healed into
`status: needs_review`, `review_reason: missing_acceptance_criteria` rather
than silently accepted. Existing `story_tree_items` rows (plain-string
`acceptance_criteria` values from before this change) were migrated
in-place to single-element JSON arrays so the column read back as `List[str]`
without a crash; the pipeline's dedup/insert logic did not need to change,
since it never reads or compares `acceptance_criteria` values.

**RBP Matrix (FR-11a).** Pulled forward from Phase 2 once real fields/rules
made it obvious what roles like "Inspector" or "Account Clerk" could and
couldn't do — `generate_rbp_matrix` follows the same additive/dedup pattern
as `generate_stories`, keyed on `(role, entity)` instead of `(entity,
name)`. One wrinkle unique to RBP: it was added after fields/stories
generation already existed, so a project drafted earlier has fields/stories
but zero RBP rows, and normally would never get any — there's no "new
transcript" to trigger a fresh rules pass. `DraftGenerationSession` detects
this (`existing_rbp_count == 0` and a draft already exists) and runs a
one-time backfill: re-extracts rules from the *full* transcript history
(not just new material) solely to feed RBP generation, without touching
fields or stories at all. Fires at most once per project — after that,
its existing_rbp_count is nonzero. `role` values are taken verbatim from
whatever the rules/stories call them (no canonical role list) — the same
concept named "Contact" in one context and "Caller" in another (see
`extract_fields_from_transcript` above) is a fully general risk, not
specific to fields; roles are equally susceptible to that drift because
`generate_rbp_matrix` is a separate LLM call from `generate_stories`.

**Process Flow (FR-11b).** `generate_process_flow` is draft generation, not
extraction, and deliberately asymmetric with fields/stories/RBP: it is a
single call over the *full* transcript text that returns a complete
`ProcessFlow` (steps + transitions) in one shot, rather than something the
pipeline incrementally extends. Two reasons this isn't additive like the
others: (1) a flowchart's value is the shape of the whole sequence — a
merge that only appends new steps from a follow-up meeting can't correct an
earlier step's position or a transition that a later meeting reveals was
wrong, the way a flat list of fields or rules can just gain new rows; (2)
`step_key` values are invented fresh per call with no cross-call identity,
so a second call has no way to know "step_3 from run 1" and "step_2 from
run 2" are the same node to merge against. `DraftGenerationSession` runs it
at most once per project — gated on `process_flow_steps` being empty for
that project (`needs_process_flow`), independent of whether new files
triggered the rest of the run — mirroring RBP's one-time-backfill mechanism
in shape (a project drafted before this feature existed gets one generated
on its next run) but simpler, since there's no "new rules to re-extract"
step to gate separately. Known limitation: unlike every other artifact in
this tool, a follow-up meeting's transcript does not update an
already-generated Process Flow, even if it describes a materially different
process — the tab reflects only what was known as of the first successful
generation. Regenerating it (e.g. by clearing that project's
`process_flow_steps` rows) is a manual, unbuilt operation in V1.

- **`APIKeyEngine`** — Anthropic Console API key, tool-use with a forced
  schema. Structured output is guaranteed by the API. Build this first —
  it's the simpler path and gives a known-good baseline.
- **`ClaudeCodeCLIEngine`** — async subprocess call to `claude -p`
  (must be async; a blocking call stalls FastAPI's event loop). Revised from
  the original plan once implemented: the CLI turns out to support
  `--output-format json --json-schema '<schema>'`, which validates the
  response against a JSON Schema server-side and returns it pre-parsed in a
  `structured_output` field — a real schema guarantee from the CLI itself,
  not just from the API. This engine uses that flag with the same JSON
  Schema `APIKeyEngine`'s tool definition uses, and still retries once with
  a stricter prompt if `is_error`/`subtype` indicates the call didn't
  succeed, before failing. Surfaces a clear "run `claude /login` again"
  message on an expired-session subprocess failure, not a raw error.
  Legitimate "ordinary individual use"
  of Claude Code for a single-operator tool — validate its output against
  `APIKeyEngine`'s on the same fixture before trusting it standalone.
  Also discovered wiring this into the real pipeline: uploaded files live
  under `data/uploads/`, outside the CLI's default trusted directory (its
  cwd), and a screenshot read there silently fails permission — the model
  answers with an empty result instead of an error, no exception raised.
  Fixed by always passing `--add-dir <UPLOAD_DIR>` on every invocation.

Both engines return identical `FieldCandidate`/`Rule` types. Nothing
downstream — extraction pipeline, review screen, traceability index — knows
or needs to know which engine ran.

## 6. Non-Functional Requirements

- **Data handling:** synthetic/genericized data only, in every example,
  fixture, and test — no real client data, ever.
- **Retention:** nothing retained beyond local storage under the user's own
  control.
- **Multi-tenancy:** not needed now; schema hangs off `project_id`
  throughout so it doesn't preclude adding it later (§4).
- **Accessibility:** keyboard-navigable, visible focus states — carried
  over from the prototype.

## 7. Build Order

See `roadmap.md` for phase-level detail (Phase 0–4). This is the
V1 sequence:

1. Data model (§4).
2. TR-1 through TR-4 — local access, Claude engine config, `.gitignore`.
3. Project CRUD, backed by the database (wire the existing prototype
   screens to real records).
4. Upload handling.
5. `APIKeyEngine`, tested against the canonical fixture (see functional
   spec §5 for the scenario; the exact data lives in the deck and
   prototype).
6. `ClaudeCodeCLIEngine`, validated against `APIKeyEngine`'s output on the
   same fixture.
7. Chat and consultant notes, persisted to the database.
8. Phase 2: ADO push, process flow generation. (RBP drafting was pulled
   forward and implemented ahead of schedule — see §5.)

## 8. Open Technical Questions

- **Audio transcription:** deferred; V1 assumes pre-transcribed text input.
- **Salesforce adapter:** architected for, not implemented in V1.
- **Auth:** deliberately not built in V1 — the rest of the stack (SQLite,
  local file storage) is single-operator only, so multi-user auth would be
  a security boundary with nothing on either side of it. If ever needed:
  add `users` + `user_id` FK (§4) and session-based auth with
  `passlib[bcrypt]` for password hashing. Both are additive.
