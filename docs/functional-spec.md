# Wherefore — Functional Specification

**Audience:** anyone evaluating what the product does — a reviewer, an
interviewer, you. Describes behavior, not implementation. See
`technical-spec.md` for architecture, stack, and data model.

---

## 1. Overview

Wherefore turns raw discovery material — call transcripts, screenshots of
an existing system — into structured delivery artifacts a functional
consultant needs: a Field Listing, a Story Tree (Epic → Feature → Story →
Acceptance Criteria), and an RBP Matrix. Every generated item carries a
pointer back to its source.

## 2. Goals & Non-Goals

**Goals**
- A genuinely useful personal tool for D365/Salesforce consulting work.
- Demonstrate real product and engineering capability for a portfolio.
- Private repo; shared selectively, not operated as a public service.

**Non-goals**
- Not commercialized — no payment processing, no public registration.
- V1 excludes: ADO/backlog auto-push, process flow diagrams, test case
  generation (Phase 2+). RBP matrix drafting was originally scoped for
  Phase 2 but was pulled forward and implemented — see FR-11a.

## 3. Target User

A functional/technology consultant delivering Dynamics 365 or Salesforce
engagements — currently, the builder herself. Works from discovery call
recordings, screenshots of the current system, and walkthrough notes;
currently builds Field Listings, Story Trees, and RBP Matrices by hand.

## 4. Interaction Model: Copilot, Not Tool or Agent

| | Tool | AI Agent | **Wherefore (this product)** |
|---|---|---|---|
| Behavior | Fixed input → fixed output | Plans, branches, acts on its own judgment | AI drafts each step; human approves before anything moves forward |

The user-facing consequence of this choice: **nothing is ever finalized,
changed, or pushed anywhere without an explicit approval action.** Chat can
suggest, extraction can draft, but only the consultant's click makes
anything real. This governs every functional requirement below.

## 5. End-to-End User Flow

1. **Open the tool, start or resume a project.** Lands on the Dashboard.
   New Project: name it, pick the target platform (D365 or Salesforce). Or
   reopen an existing project, resuming where it was left off.
2. **Upload the discovery material** — transcript and screenshots from the
   discovery call or system walkthrough.
3. **Add anything the recording missed**, via chat, available at this stage
   and every other. Logged as a consultant note — never silently merged
   into a draft.
4. **Extraction runs** — fields and business rules are pulled out, each
   tagged with exactly where it came from.
5. **Review the draft** — Field Listing, Story Tree, and RBP Matrix in
   tabs, pre-filled. Most items auto-approved; low-confidence ones flagged.
6. **Check anything that looks off** — click a Source for the exact
   citation, or ask chat directly, grounded in the real draft on screen.
7. **Approve, and eventually push** — approve now; Phase 2 adds pushing
   directly into the backlog tool with hierarchy intact.
8. **Come back later** — during UAT, the Traceability Index answers "why
   does this exist" in one click instead of a recording search.

## 6. Functional Requirements

**Project management**
- FR-1 Create a project: name + target platform.
- FR-2 Dashboard lists projects with a status pill (Draft / In Review / Pushed).
- FR-3 Reopen an existing project and resume.

**Upload & intake**
- FR-4 Upload a discovery transcript (V1: text only; audio transcription
  deferred).
- FR-5 Upload one or more screenshots.
- FR-5a Upload one or more video recordings (e.g. a recorded client
  meeting). Stored and playable back within the project; not yet
  transcribed or fed into extraction — see FR-4's audio deferral, which
  this inherits.
- FR-6 Uploaded files are used only for extraction (or, for video
  recordings, playback within the tool), never sent elsewhere.

**Extraction**
- FR-7 Screenshots are read for field candidates: name, inferred type,
  required, layout position, and the target entity/section they belong to
  (e.g. a field on a separate caller-details form is attributed to the
  Contact entity, not Case).
- FR-7a Transcripts are also read for field candidates directly — a
  brand-new system discussed only in conversation has no legacy UI to
  screenshot at all, so field extraction cannot be screenshot-only. A field
  described in both a screenshot and the transcript is shown once, with a
  combined source citation naming both, not as two separate rows.
- FR-7b Every field typed as a Lookup names the entity it looks up to — a
  Lookup with no stated target isn't something a developer can build, so
  this is not optional. If that target entity doesn't already have fields
  of its own in the Field Listing, its own primary field is added too, so
  the listing is complete enough to build every entity it references, not
  just the ones with a visible form. A Lookup drafted without a resolvable
  target is flagged for review rather than left silently incomplete.
- FR-7c A field is marked required based on real evidence it's mandatory —
  an explicit indicator, an explicit statement, or the field being clearly
  load-bearing for the record to exist at all — not defaulted to "not
  required" just because nothing explicitly said so.
- FR-7d Every entity has at most one field marked as its primary/identifying
  field (the field a human would recognize a record by), so a consultant
  and a developer both know what a lookup search on that entity would show.
  Not every entity necessarily has one — a platform-auto-numbered record is
  left with none rather than a guessed one.
- FR-7e Every Choice/Picklist field lists its actual option values as
  structured data on the Field Listing, not only mentioned in passing
  narrative — a developer configuring the option set needs the real list,
  not a citation that happens to mention some of them.
- FR-8 Transcripts are parsed for business rules, exceptions, and role
  mentions, each tagged with a source timestamp.
- FR-9 Extraction runs with visible, step-by-step progress.

**Draft generation**
- FR-10 Field Listing generated, typed per the active platform, and grouped
  by target entity so a consultant can see where each field belongs, not
  just what it is.
- FR-11 Story Tree generated as Epic → Feature → Story → Acceptance Criteria.
- FR-11c Each story carries multiple acceptance criteria, not one — the
  primary/happy-path case plus whatever exception, boundary, or
  validation/negative case the source rules actually describe (e.g. "the
  case cannot be closed while unassigned" alongside "the case is
  successfully closed once assigned"). A rule that only supports a single
  testable condition still produces a story with one criterion — the model
  is not asked to pad the list to hit a count.
- FR-11a RBP Matrix generated: for every role mentioned in the extracted
  rules/stories, which entities it can Create/Read/Update/Delete/Reassign,
  with a stated scope when read access is restricted (e.g. "own records
  only"). A role or capability not evidenced in the source material is not
  invented — an ungranted permission is the default, not a guess. Follows
  the same additive/dedup rules as FR-12a: a role/entity pair already
  recorded is never re-derived or overwritten by a later run.
- FR-11b Process Flow generated: the CURRENT (as-is) business process
  described in the discovery transcript, mapped as a sequence of steps and
  transitions (a flowchart), distinct from the Story Tree's future/to-be
  system. Each step names the actor performing it and its type (start /
  task / decision / end); each transition between two steps carries the
  condition that triggers it, when one applies (e.g. a branch out of a
  decision step). Generated once per project, from the full transcript
  history available at that point — unlike the Field Listing, RBP Matrix,
  and Story Tree, a later follow-up-meeting run does not attempt to merge
  new material into an already-generated flow (see technical spec §5's
  limitations note). A project that already had a draft before this
  feature existed gets one generated on its next draft run, from all
  transcripts uploaded so far.
- FR-12 Every generated item stores a pointer back to its origin — the
  specific uploaded file plus a detail reference (timestamp, cell, form
  region), not just a display string.
- FR-12a A project already in review supports follow-up discovery material
  (another meeting's transcript and/or screenshots). Generating a draft
  again after new uploads only adds fields/stories for what's new — it
  never deletes, overwrites, or re-flags an item from a previous run, so a
  consultant's prior review work is never silently undone. A field
  described again in the new material (same entity + name as an existing
  one) is not duplicated.

**Review & traceability**
- FR-13 Draft Review shows Field Listing / Process Flow / Story Tree / RBP
  Matrix in tabs, in that order.
- FR-14 Clicking a Source opens a panel with the exact citation and a
  plain-language explanation.
- FR-15 Items are flagged for manual review with a stated reason —
  low confidence, or the extraction being unable to confidently assign an
  entity or source form (e.g. two forms use conflicting names for what may
  be the same field).
- FR-16 Traceability Index: every drafted item across all projects,
  independently browsable.

**Chat & consultant notes**
- FR-17 Chat is available on every screen, contextual to the current
  project/view/field.
- FR-18 Chat is grounded in the current project's real data.
- FR-19 "Add as consultant note" logs a chat message against the draft;
  nothing changes automatically.
- FR-20 Notes persist and are visible on the Field Listing tab.

**Approve & push (Phase 2)**
- FR-21 "Approve All & Continue" marks the project reviewed.
- FR-22 Approved stories push to the backlog tool, preserving the
  Epic/Feature/Story hierarchy.

## 7. Success Criteria (V1)

- Running extraction against the canonical fixture produces a Field Listing
  and Story Tree that need light editing, not a rewrite.
- The full loop — create project → upload → extract → review → approve —
  works end to end on real extraction, not scripted data.

## 8. Open Product Questions

- **License:** decided — source-available (not open source), free for
  individuals and organizations under 5 people, commercial license required
  above that, converting to AGPL-3.0 on 2030-09-07. See `LICENSE` at repo
  root and CLAUDE.md's Core Decisions.
