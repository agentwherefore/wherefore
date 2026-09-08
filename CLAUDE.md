# Wherefore — Project Context for Claude Code

Read this first, every session. Read `docs/functional-spec.md` and
`docs/technical-spec.md` before writing any code — they are the
source of truth (functional = what it does, technical = how it's built),
this file is the quick-reference layer on top of them. `PRD.md` has been
split into these two documents and can be deleted from the repo.

## What this is

Wherefore turns raw discovery material (call transcripts, screenshots of an
existing system) into structured delivery artifacts a functional consultant
needs: a Field Listing, a Story Tree (Epic → Feature → Story → AC), and an
RBP Matrix — every generated item traceable back to its source.

## Scope — read this before adding anything

- **Private portfolio/demo project.** Not commercialized. Not operated as a
  public service. One user: the builder.
- **Single-operator by design.** SQLite, local file storage, no
  multi-tenancy. **Do not add auth, registration, or multi-user features
  without being asked.** An earlier draft of this project included full
  registration/login/session auth "for completeness" — it was wrong, because
  it contradicted every other layer of the stack, which only supports one
  operator. That's the standing lesson: check whether a feature matches the
  actual deployment shape before adding it. Don't default to commercial-SaaS
  patterns reflexively.
- **Synthetic data only, always.** No real client data in any fixture,
  example, test, or commit — full stop, no exceptions.

## Core decisions (already made — don't relitigate without new information)

- **Copilot, not Tool or Agent.** AI drafts at every step; a human approves
  before anything is finalized or pushed anywhere. No autonomous action.
- **Core + Adapters architecture.** Platform-agnostic core (intake,
  extraction, story/test generation, traceability engine). D365 is the first
  platform adapter; Salesforce is designed-for but not built. ADO is the
  first backlog adapter.
- **Dual Claude access engines**, behind one `ExtractionEngine` interface:
  - `APIKeyEngine` — Anthropic Console API key, tool-use with a forced
    schema. Build this first; it's the simpler, guaranteed-structured path.
  - `ClaudeCodeCLIEngine` — async subprocess to `claude -p`. Legitimate
    "ordinary individual use" for a single-operator tool, but has no schema
    guarantee from the CLI itself — needs its own JSON-extraction, schema
    validation, and one retry with a stricter formatting instruction before
    failing. Surface expired-session errors as "run `claude /login` again,"
    not a raw subprocess error.
  - Both engines return identical types. Nothing downstream should know or
    care which one ran.

## Tech stack

FastAPI (Python) · SQLite · vanilla HTML/CSS/JS frontend, served as a single
static file (`backend/app/static/index.html`) — evolve it in place rather
than rewriting; reach for a framework only if state management genuinely
demands it · local filesystem for uploads.

## Canonical test fixture

Use this exact scenario for all early testing — it's already the reference
data across the deck, prototype, and specs, so keep it consistent rather
than
inventing new synthetic data:

Acme Field Ops Case Management, target platform D365. A call center's intake
process: agents log Caller Name, Phone, Call Reason, Status, Assigned To.
Urgent/safety calls must be assigned within 15 minutes. Agents see only
their own cases; Supervisors see and can reassign all cases. Call Reason
categories change quarterly — the transcript line at 04:12 is what makes
this a Lookup rather than a static Choice, and is the canonical example of
the traceability feature working.

## Build order (see technical spec §7 and §4 for full detail)

1. Data model (technical spec §4) — no `users` table.
2. TR-1 through TR-4 — local-only access, Claude engine config, `.gitignore`
   for the API key.
3. Project CRUD, backed by the database (wire the existing prototype
   screens to real records).
4. Upload handling.
5. `APIKeyEngine`, tested against the canonical fixture above.
6. `ClaudeCodeCLIEngine`, validated against `APIKeyEngine`'s output on the
   same fixture.
7. Chat and consultant notes, persisted (not in-memory).
8. Phase 2: ADO push, RBP drafting, process flow generation.

## Working conventions

- `docs/functional-spec.md` and `docs/technical-spec.md` are
  living documentation. When a decision changes during the build — the way
  several already have in the design conversation this project came out
  of — update the relevant requirement or Open Questions section rather
  than letting the code and the docs drift apart.
- When scope is ambiguous, check the specs first. If it's genuinely not
  covered, ask rather than assuming a fuller-featured default is safer —
  the auth mistake above is exactly what over-assuming looks like.
- Deferred, on purpose, not by oversight: audio transcription, the
  Salesforce adapter implementation. Don't build toward these without being
  asked.
- **Source-available (not open source), free under 5 people, commercial
  license above that.** See `LICENSE` at repo root — the "Wherefore Source
  License 1.0," adapted from the Business Source License 1.1 template
  (mariadb.com/bsl11), not AGPL-3.0 outright. AGPL-3.0 itself can't carry a
  usage restriction and still legally be AGPL-3.0 or qualify as open
  source — that's why this isn't just "AGPL-3.0 with a note." The
  Additional Use Grant in LICENSE lets individuals and organizations under
  5 total people use it for anything; everyone else needs a commercial
  license, requested via the published Google Form linked in LICENSE. The
  license automatically converts to AGPL-3.0 (full text at
  `licenses/AGPL-3.0.txt`) on the Change Date, 2030-09-07 — chosen so the
  network-use gap (a hosted fork must release its source) still applies
  even after conversion. Per BSL's own design, each new release should get
  a fresh Change Date in its own LICENSE file — that's the mechanism for
  keeping the current version under commercial terms indefinitely while
  older versions age into full AGPL-3.0 on schedule; don't just edit this
  Change Date in place for the same version, that breaks the commitment
  the license makes to existing users of it.
