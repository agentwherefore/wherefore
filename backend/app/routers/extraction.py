import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..extraction.pipeline import get_session, start_session

router = APIRouter()


@router.post("/{project_id}/generate-draft")
async def generate_draft(project_id: int, db: Session = Depends(get_db)):
    project = db.get(models.Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    session = await start_session(project_id)
    return {"status": "running" if session.running else "started"}


@router.get("/{project_id}/generate-draft/stream")
async def stream_generate_draft(project_id: int):
    session = get_session(project_id)

    async def event_gen():
        sent = 0
        while True:
            if len(session.events) > sent:
                for event in session.events[sent:]:
                    yield f"data: {json.dumps(event)}\n\n"
                sent = len(session.events)
            if session.done and sent >= len(session.events):
                break
            await asyncio.sleep(0.3)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.get("/{project_id}/draft")
async def get_draft(project_id: int, db: Session = Depends(get_db)):
    project = db.get(models.Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    fields = (
        db.query(models.FieldListingItem)
        .filter(models.FieldListingItem.project_id == project_id)
        .order_by(models.FieldListingItem.id)
        .all()
    )
    stories = (
        db.query(models.StoryTreeItem)
        .filter(models.StoryTreeItem.project_id == project_id)
        .order_by(models.StoryTreeItem.id)
        .all()
    )
    rbp_entries = (
        db.query(models.RbpMatrixItem)
        .filter(models.RbpMatrixItem.project_id == project_id)
        .order_by(models.RbpMatrixItem.id)
        .all()
    )
    flow_steps = (
        db.query(models.ProcessFlowStep)
        .filter(models.ProcessFlowStep.project_id == project_id)
        .order_by(models.ProcessFlowStep.id)
        .all()
    )
    flow_transitions = (
        db.query(models.ProcessFlowTransition)
        .filter(models.ProcessFlowTransition.project_id == project_id)
        .order_by(models.ProcessFlowTransition.id)
        .all()
    )

    def field_out(f: models.FieldListingItem) -> dict:
        return {
            "id": f.id,
            "name": f.name,
            "field_type": f.field_type,
            "required": f.required,
            "entity": f.entity,
            "section": f.section,
            "lookup_target_entity": f.lookup_target_entity,
            "choice_values": f.choice_values,
            "is_primary_field": f.is_primary_field,
            "source_type": f.source_type,
            "source_filename": f.source_file.filename if f.source_file else None,
            "source_detail": f.source_detail,
            "status": f.status,
            "review_reason": f.review_reason,
            "rationale": f.rationale,
        }

    def story_out(s: models.StoryTreeItem) -> dict:
        return {
            "id": s.id,
            "epic": s.epic,
            "feature": s.feature,
            "story": s.story,
            "acceptance_criteria": s.acceptance_criteria,
            "source_filename": s.source_file.filename if s.source_file else None,
            "source_detail": s.source_detail,
            "status": s.status,
            "review_reason": s.review_reason,
        }

    def rbp_out(r: models.RbpMatrixItem) -> dict:
        return {
            "id": r.id,
            "role": r.role,
            "entity": r.entity,
            "can_create": r.can_create,
            "can_read": r.can_read,
            "read_scope": r.read_scope,
            "can_update": r.can_update,
            "can_delete": r.can_delete,
            "can_reassign": r.can_reassign,
            "source_filename": r.source_file.filename if r.source_file else None,
            "source_detail": r.source_detail,
            "status": r.status,
            "review_reason": r.review_reason,
        }

    def flow_step_out(s: models.ProcessFlowStep) -> dict:
        return {
            "id": s.id,
            "step_key": s.step_key,
            "label": s.label,
            "actor": s.actor,
            "step_type": s.step_type,
            "source_filename": s.source_file.filename if s.source_file else None,
            "source_detail": s.source_detail,
            "status": s.status,
            "review_reason": s.review_reason,
        }

    def flow_transition_out(t: models.ProcessFlowTransition) -> dict:
        return {
            "id": t.id,
            "from_step": t.from_step_key,
            "to_step": t.to_step_key,
            "condition": t.condition,
        }

    return {
        "fields": [field_out(f) for f in fields],
        "stories": [story_out(s) for s in stories],
        "rbp": [rbp_out(r) for r in rbp_entries],
        "process_flow": {
            "steps": [flow_step_out(s) for s in flow_steps],
            "transitions": [flow_transition_out(t) for t in flow_transitions],
        },
    }
