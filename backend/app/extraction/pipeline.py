import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .. import models
from ..database import SessionLocal
from .factory import get_engine
from .schemas import FieldCandidate, StoryItem


class DraftGenerationSession:
    """Tracks one project's in-flight draft generation.

    Additive/incremental by design: a run only ever adds new fields/stories
    for genuinely new material (new or previously-unprocessed uploads) —
    it never deletes or modifies an existing field_listing_items or
    story_tree_items row, so an already-reviewed item is never silently
    changed by a later follow-up meeting's upload. This mirrors the
    product's core rule that nothing changes without a human approving it.

    Single-operator tool — one run per project at a time is all that's ever
    meaningful, so this is process-local state, not a DB table (same
    approach as ClaudeLoginSession).
    """

    def __init__(self) -> None:
        self.events: List[dict] = []
        self.running = False
        self.done = False
        self.success: Optional[bool] = None
        self.error: Optional[str] = None
        self.message: Optional[str] = None

    def _emit(self, event: dict) -> None:
        self.events.append(event)

    async def run(self, project_id: int) -> None:
        self.events = []
        self.running = True
        self.done = False
        self.success = None
        self.error = None
        self.message = None

        db = SessionLocal()
        try:
            project = db.get(models.Project, project_id)
            if not project:
                raise RuntimeError("Project not found")

            files = (
                db.query(models.UploadedFile)
                .filter(models.UploadedFile.project_id == project_id)
                .all()
            )
            screenshots = [f for f in files if f.type == "screenshot"]
            transcripts = [f for f in files if f.type == "transcript"]

            if not screenshots and not transcripts:
                raise RuntimeError(
                    "Upload at least one transcript or screenshot before generating a draft."
                )

            new_screenshots = [f for f in screenshots if f.processed_at is None]
            new_transcripts = [f for f in transcripts if f.processed_at is None]

            # RBP generation was added after fields/stories generation
            # existed — a project drafted before that has fields/stories but
            # no RBP entries, and no "new" material to trigger a fresh rules
            # pass. Without this, RBP would silently never run for it. This
            # only fires once (existing_rbp_count stays 0 until it runs).
            existing_rbp_count = (
                db.query(models.RbpMatrixItem)
                .filter(models.RbpMatrixItem.project_id == project_id)
                .count()
            )
            has_existing_draft = (
                db.query(models.FieldListingItem).filter(models.FieldListingItem.project_id == project_id).count() > 0
                or db.query(models.StoryTreeItem).filter(models.StoryTreeItem.project_id == project_id).count() > 0
            )
            needs_rbp_backfill = existing_rbp_count == 0 and has_existing_draft and bool(transcripts)

            # Process flow is generated once per project, ever — from the
            # full transcript history, not just new material — since there's
            # no well-defined way to merge new steps into an already-drawn
            # flow without a human re-reviewing the whole diagram. So this
            # fires whenever no flow exists yet and any transcript exists,
            # regardless of whether this run has "new" material.
            existing_flow_step_count = (
                db.query(models.ProcessFlowStep)
                .filter(models.ProcessFlowStep.project_id == project_id)
                .count()
            )
            needs_process_flow = existing_flow_step_count == 0 and bool(transcripts)

            if not new_screenshots and not new_transcripts and not needs_rbp_backfill and not needs_process_flow:
                self._emit({"type": "step", "step": "screenshots", "status": "done"})
                self._emit({"type": "step", "step": "transcript", "status": "done"})
                self._emit({"type": "step", "step": "fields", "status": "done"})
                self._emit({"type": "step", "step": "stories", "status": "done"})
                self._emit({"type": "step", "step": "rbp", "status": "done"})
                self._emit({"type": "step", "step": "process_flow", "status": "done"})
                self.success = True
                self.message = "No new material since the last update — nothing to add."
                return

            engine = get_engine()

            # Full history (old + new) — free to read, used only as context
            # for typing decisions on new screenshots. New-only text is used
            # for the actual rules/transcript-field LLM calls below, so a
            # follow-up run doesn't re-derive (and re-story) content already
            # captured from earlier meetings.
            full_transcript_text = (
                "\n\n".join(Path(t.storage_path).read_text() for t in transcripts)
                if transcripts
                else None
            )
            new_transcript_text = (
                "\n\n".join(Path(t.storage_path).read_text() for t in new_transcripts)
                if new_transcripts
                else None
            )

            # Existing fields, queried up front so a follow-up run's
            # extraction calls can be told what's already known — otherwise
            # the same field can come back reclassified under a different
            # entity, which the (entity, name) dedup key below wouldn't catch
            # since it'd look like a different field entirely.
            existing_items = (
                db.query(models.FieldListingItem)
                .filter(models.FieldListingItem.project_id == project_id)
                .all()
            )
            existing_keys = {
                (item.entity.strip().lower(), item.name.strip().lower()) for item in existing_items
            }
            by_entity: Dict[str, List[str]] = {}
            primary_by_entity: Dict[str, str] = {}
            for item in existing_items:
                by_entity.setdefault(item.entity, []).append(item.name)
                if item.is_primary_field:
                    primary_by_entity[item.entity.strip().lower()] = item.name

            def render_fields_context() -> Optional[str]:
                if not by_entity:
                    return None
                lines = []
                for entity, names in by_entity.items():
                    primary_name = primary_by_entity.get(entity.strip().lower())
                    labeled = [n + (" (primary)" if n == primary_name else "") for n in names]
                    lines.append(f"- {entity}: {', '.join(labeled)}")
                return "\n".join(lines)

            def dedupe_primary(candidate) -> None:
                # Deterministic backstop: never let a second field on the
                # same entity claim is_primary_field, regardless of what the
                # model returned — an entity has at most one primary field.
                if not candidate.is_primary_field:
                    return
                key = candidate.entity.strip().lower()
                if key in primary_by_entity:
                    candidate.is_primary_field = False
                else:
                    primary_by_entity[key] = candidate.name

            self._emit({"type": "step", "step": "screenshots", "status": "active", "total": len(new_screenshots)})
            field_rows = []
            for shot in new_screenshots:
                fields = await engine.extract_fields(shot.storage_path, full_transcript_text, render_fields_context())
                for f in fields:
                    dedupe_primary(f)
                    field_rows.append({"candidate": f, "source_type": "screenshot", "source_file_id": shot.id})
                    # So the transcript-field extraction call below (a
                    # separate LLM call with no shared memory) doesn't
                    # reclassify a field this run's screenshot step already
                    # found under a different entity.
                    by_entity.setdefault(f.entity, []).append(f.name)
            self._emit({"type": "step", "step": "screenshots", "status": "done"})

            self._emit({"type": "step", "step": "transcript", "status": "active"})
            rules = []
            if new_transcript_text:
                rules = await engine.extract_rules(new_transcript_text)
                transcript_fields = await engine.extract_fields_from_transcript(
                    new_transcript_text, render_fields_context()
                )
                for f in transcript_fields:
                    dedupe_primary(f)
                primary_new_transcript = new_transcripts[0]
                field_rows.extend(
                    {
                        "candidate": f,
                        "source_type": "transcript",
                        "source_file_id": primary_new_transcript.id,
                    }
                    for f in transcript_fields
                )
            self._emit({"type": "step", "step": "transcript", "status": "done"})

            self._emit({"type": "step", "step": "fields", "status": "active"})
            # Merge candidates found in both sources *this run* by
            # (entity, name); screenshot rows were appended first so its
            # typing wins when both agree on a field.
            merged: Dict[tuple, dict] = {}
            merge_order: List[tuple] = []
            for row in field_rows:
                key = (row["candidate"].entity.strip().lower(), row["candidate"].name.strip().lower())
                if key not in merged:
                    merged[key] = {"candidate": row["candidate"], "sources": [row]}
                    merge_order.append(key)
                else:
                    merged[key]["sources"].append(row)

            # Cross-run dedup: skip anything already recorded in a previous
            # run — never touch or overwrite an existing row.
            for key in merge_order:
                if key in existing_keys:
                    continue
                entry = merged[key]
                f = entry["candidate"]
                sources = entry["sources"]
                if len(sources) > 1:
                    source_type = "+".join(sorted({s["source_type"] for s in sources}))
                    source_file_id = sources[0]["source_file_id"]
                    source_detail = " · ".join(
                        ("Screenshot" if s["source_type"] == "screenshot" else "Transcript")
                        + ": " + s["candidate"].source_detail
                        for s in sources
                    )
                else:
                    source_type = sources[0]["source_type"]
                    source_file_id = sources[0]["source_file_id"]
                    source_detail = f.source_detail
                db.add(models.FieldListingItem(
                    project_id=project_id,
                    name=f.name,
                    field_type=f.field_type,
                    required=f.required,
                    entity=f.entity,
                    section=f.section,
                    lookup_target_entity=f.lookup_target_entity,
                    choice_values=f.choice_values,
                    is_primary_field=f.is_primary_field,
                    source_type=source_type,
                    source_file_id=source_file_id,
                    source_detail=source_detail,
                    status=f.status,
                    review_reason=f.review_reason,
                    rationale=f.rationale,
                ))
            db.commit()
            self._emit({"type": "step", "step": "fields", "status": "done"})

            self._emit({"type": "step", "step": "stories", "status": "active"})
            # Ground story/RBP generation in the *complete* field list
            # (old + new) so they can reference already-known fields, not
            # just ones from this run. Built unconditionally — the RBP
            # backfill path below needs it even when there are no new rules.
            all_fields = [
                FieldCandidate(
                    name=item.name,
                    field_type=item.field_type,
                    required=item.required,
                    entity=item.entity,
                    section=item.section,
                    lookup_target_entity=item.lookup_target_entity,
                    choice_values=item.choice_values,
                    is_primary_field=item.is_primary_field,
                    source_detail=item.source_detail or "",
                    status=item.status,
                    review_reason=item.review_reason,
                    rationale=item.rationale or "",
                )
                for item in db.query(models.FieldListingItem)
                .filter(models.FieldListingItem.project_id == project_id)
                .all()
            ]
            stories = []
            if rules:
                stories = await engine.generate_stories(all_fields, rules, project.target_platform)

            primary_new_transcript = new_transcripts[0] if new_transcripts else None
            for s in stories:
                db.add(models.StoryTreeItem(
                    project_id=project_id,
                    epic=s.epic,
                    feature=s.feature,
                    story=s.story,
                    acceptance_criteria=s.acceptance_criteria,
                    source_file_id=primary_new_transcript.id if primary_new_transcript else None,
                    source_detail=s.source_detail,
                    status=s.status,
                    review_reason=s.review_reason,
                ))
            db.commit()
            self._emit({"type": "step", "step": "stories", "status": "done"})

            self._emit({"type": "step", "step": "rbp", "status": "active"})
            rules_for_rbp = rules
            if needs_rbp_backfill and not rules_for_rbp:
                # No new transcript this run, but this project has never had
                # RBP generated — derive rules from the full history once so
                # it isn't permanently skipped.
                rules_for_rbp = await engine.extract_rules(full_transcript_text)
            if rules_for_rbp:
                existing_rbp = (
                    db.query(models.RbpMatrixItem)
                    .filter(models.RbpMatrixItem.project_id == project_id)
                    .all()
                )
                existing_rbp_keys = {
                    (r.role.strip().lower(), r.entity.strip().lower()) for r in existing_rbp
                }
                rbp_by_role: Dict[str, List[str]] = {}
                for r in existing_rbp:
                    rbp_by_role.setdefault(r.role, []).append(r.entity)
                existing_grants_context = (
                    "\n".join(f"- {role}: {', '.join(entities)}" for role, entities in rbp_by_role.items())
                    if rbp_by_role else None
                )

                all_stories = [
                    StoryItem(
                        epic=item.epic,
                        feature=item.feature,
                        story=item.story,
                        acceptance_criteria=item.acceptance_criteria or "",
                        source_detail=item.source_detail or "",
                        status=item.status,
                        review_reason=item.review_reason,
                    )
                    for item in db.query(models.StoryTreeItem)
                    .filter(models.StoryTreeItem.project_id == project_id)
                    .all()
                ]
                rbp_entries = await engine.generate_rbp_matrix(
                    all_fields, rules_for_rbp, all_stories, project.target_platform, existing_grants_context
                )
                primary_new_transcript_rbp = new_transcripts[0] if new_transcripts else None
                for r in rbp_entries:
                    key = (r.role.strip().lower(), r.entity.strip().lower())
                    if key in existing_rbp_keys:
                        continue
                    db.add(models.RbpMatrixItem(
                        project_id=project_id,
                        role=r.role,
                        entity=r.entity,
                        can_create=r.can_create,
                        can_read=r.can_read,
                        read_scope=r.read_scope,
                        can_update=r.can_update,
                        can_delete=r.can_delete,
                        can_reassign=r.can_reassign,
                        source_file_id=primary_new_transcript_rbp.id if primary_new_transcript_rbp else None,
                        source_detail=r.source_detail,
                        status=r.status,
                        review_reason=r.review_reason,
                    ))
                db.commit()
            self._emit({"type": "step", "step": "rbp", "status": "done"})

            self._emit({"type": "step", "step": "process_flow", "status": "active"})
            if needs_process_flow:
                flow = await engine.generate_process_flow(full_transcript_text, project.target_platform)
                flow_source_file = new_transcripts[0] if new_transcripts else transcripts[0]
                for s in flow.steps:
                    db.add(models.ProcessFlowStep(
                        project_id=project_id,
                        step_key=s.step_key,
                        label=s.label,
                        actor=s.actor,
                        step_type=s.step_type,
                        source_file_id=flow_source_file.id,
                        source_detail=s.source_detail,
                        status=s.status,
                        review_reason=s.review_reason,
                    ))
                for t in flow.transitions:
                    db.add(models.ProcessFlowTransition(
                        project_id=project_id,
                        from_step_key=t.from_step,
                        to_step_key=t.to_step,
                        condition=t.condition,
                    ))
                db.commit()
            self._emit({"type": "step", "step": "process_flow", "status": "done"})

            now = datetime.now(timezone.utc)
            for f in new_screenshots + new_transcripts:
                f.processed_at = now
            project.status = "in_review"
            db.commit()
            self.success = True
        except Exception as exc:  # noqa: BLE001 — surfaced to the UI as the failure reason
            self.error = str(exc)
            self.success = False
        finally:
            db.close()
            self.done = True
            self.running = False
            self._emit({
                "type": "done",
                "success": self.success,
                "error": self.error,
                "message": self.message,
            })


_sessions: Dict[int, DraftGenerationSession] = {}


def get_session(project_id: int) -> DraftGenerationSession:
    if project_id not in _sessions:
        _sessions[project_id] = DraftGenerationSession()
    return _sessions[project_id]


async def start_session(project_id: int) -> DraftGenerationSession:
    session = get_session(project_id)
    if not session.running:
        asyncio.create_task(session.run(project_id))
    return session
