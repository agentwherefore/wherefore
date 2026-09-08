from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    target_platform = Column(String, nullable=False)  # d365 | salesforce
    status = Column(String, nullable=False, default="draft")  # draft | in_review | pushed
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    uploaded_files = relationship(
        "UploadedFile", back_populates="project", cascade="all, delete-orphan"
    )
    field_listing_items = relationship(
        "FieldListingItem", back_populates="project", cascade="all, delete-orphan"
    )
    story_tree_items = relationship(
        "StoryTreeItem", back_populates="project", cascade="all, delete-orphan"
    )
    rbp_matrix_items = relationship(
        "RbpMatrixItem", back_populates="project", cascade="all, delete-orphan"
    )
    consultant_notes = relationship(
        "ConsultantNote", back_populates="project", cascade="all, delete-orphan"
    )
    process_flow_steps = relationship(
        "ProcessFlowStep", back_populates="project", cascade="all, delete-orphan"
    )
    process_flow_transitions = relationship(
        "ProcessFlowTransition", back_populates="project", cascade="all, delete-orphan"
    )

    @property
    def has_draft(self) -> bool:
        return bool(self.field_listing_items) or bool(self.story_tree_items)


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    type = Column(String, nullable=False)  # transcript | screenshot | video_recording
    filename = Column(String, nullable=False)
    storage_path = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=utcnow, nullable=False)
    # Set once this file has contributed to a draft generation run. Lets a
    # follow-up "Update Draft" pass process only newly-added files instead
    # of re-running extraction on everything every time.
    processed_at = Column(DateTime, nullable=True)

    project = relationship("Project", back_populates="uploaded_files")


class FieldListingItem(Base):
    __tablename__ = "field_listing_items"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String, nullable=False)
    field_type = Column(String, nullable=False)
    required = Column(Boolean, default=False, nullable=False)
    entity = Column(String)  # target table this field belongs to, e.g. "Case", "Contact"
    section = Column(String)  # form/tab section within that entity, e.g. "Caller Details"
    # Required (non-null) when field_type is lookup/lookup_user — the entity
    # this field points to. A "Lookup" with no named target isn't buildable.
    lookup_target_entity = Column(String, nullable=True)
    # Required (non-empty) when field_type is "choice" — the actual option
    # values (e.g. ["New", "Assigned", "Closed"]). Stored as JSON; SQLite
    # keeps it as serialized TEXT under the hood.
    choice_values = Column(JSON, nullable=True)
    # True for at most one field per entity — the field that identifies a
    # record of that entity to a human (e.g. "Facility Name" for Facility).
    is_primary_field = Column(Boolean, default=False, nullable=False)
    source_type = Column(String, nullable=False)  # transcript | screenshot | consultant_note
    source_file_id = Column(Integer, ForeignKey("uploaded_files.id"), nullable=True)
    source_detail = Column(String)  # e.g. "04:12", "Column G", "row 14"
    status = Column(String, default="needs_review", nullable=False)  # approved | needs_review
    # Why status is needs_review, e.g. "ambiguous_entity", "ambiguous_form", "low_confidence".
    # Distinct from source_detail: this is a reason, not a citation.
    review_reason = Column(String)
    # Plain-language explanation for the trace panel — why this field was
    # typed/assigned the way it was.
    rationale = Column(Text)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    project = relationship("Project", back_populates="field_listing_items")
    source_file = relationship("UploadedFile")


class StoryTreeItem(Base):
    __tablename__ = "story_tree_items"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    epic = Column(String, nullable=False)
    feature = Column(String, nullable=False)
    story = Column(Text, nullable=False)
    # List of Given/When/Then criteria (happy path + whatever edge/validation
    # cases the source rules support) — not a single condition per story.
    acceptance_criteria = Column(JSON)
    source_file_id = Column(Integer, ForeignKey("uploaded_files.id"), nullable=True)
    source_detail = Column(String)  # e.g. "04:12" — the rule this story traces back to
    status = Column(String, default="needs_review", nullable=False)  # approved | needs_review
    review_reason = Column(String)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    project = relationship("Project", back_populates="story_tree_items")
    source_file = relationship("UploadedFile")


class RbpMatrixItem(Base):
    __tablename__ = "rbp_matrix_items"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    role = Column(String, nullable=False)
    entity = Column(String, nullable=False)
    can_create = Column(Boolean, default=False, nullable=False)
    can_read = Column(Boolean, default=False, nullable=False)
    read_scope = Column(String, nullable=True)  # e.g. "own records only"; null if unrestricted
    can_update = Column(Boolean, default=False, nullable=False)
    can_delete = Column(Boolean, default=False, nullable=False)
    can_reassign = Column(Boolean, default=False, nullable=False)
    source_file_id = Column(Integer, ForeignKey("uploaded_files.id"), nullable=True)
    source_detail = Column(String)
    status = Column(String, default="needs_review", nullable=False)  # approved | needs_review
    review_reason = Column(String)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    project = relationship("Project", back_populates="rbp_matrix_items")
    source_file = relationship("UploadedFile")


class ProcessFlowStep(Base):
    __tablename__ = "process_flow_steps"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    # Stable identifier within a project, used only to resolve
    # ProcessFlowTransition.from_step_key/to_step_key — not shown directly.
    step_key = Column(String, nullable=False)
    label = Column(String, nullable=False)
    actor = Column(String, nullable=False)  # role performing this step, or "System"
    step_type = Column(String, nullable=False)  # start | task | decision | end
    source_file_id = Column(Integer, ForeignKey("uploaded_files.id"), nullable=True)
    source_detail = Column(String)
    status = Column(String, default="needs_review", nullable=False)  # approved | needs_review
    review_reason = Column(String)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    project = relationship("Project", back_populates="process_flow_steps")
    source_file = relationship("UploadedFile")


class ProcessFlowTransition(Base):
    __tablename__ = "process_flow_transitions"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    from_step_key = Column(String, nullable=False)
    to_step_key = Column(String, nullable=False)
    condition = Column(String, nullable=True)  # e.g. "Inspection passes"; null if unconditional
    created_at = Column(DateTime, default=utcnow, nullable=False)

    project = relationship("Project", back_populates="process_flow_transitions")


class ConsultantNote(Base):
    __tablename__ = "consultant_notes"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    note_text = Column(Text, nullable=False)
    related_field_id = Column(Integer, ForeignKey("field_listing_items.id"), nullable=True)
    source = Column(String, default="chat", nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    project = relationship("Project", back_populates="consultant_notes")
