from abc import ABC, abstractmethod
from typing import List, Optional

from .schemas import FieldCandidate, ProcessFlow, RbpEntry, Rule, StoryItem


class ExtractionEngine(ABC):
    """Platform-agnostic interface both Claude access engines implement.

    Nothing downstream — extraction pipeline, review screen, traceability
    index — knows or needs to know which engine ran (technical spec §5).
    """

    @abstractmethod
    async def extract_fields(
        self,
        screenshot_path: str,
        transcript_context: Optional[str] = None,
        existing_fields_context: Optional[str] = None,
    ) -> List[FieldCandidate]:
        """`transcript_context` is the project's discovery transcript, when
        one has been uploaded. A field's correct type sometimes only becomes
        clear once the screenshot is read alongside what was said in the
        call — e.g. a dropdown with no visible options is a Lookup, not a
        Choice, once the transcript says its values change every quarter.

        `existing_fields_context` lists fields already recorded for this
        project in a prior run (grouped by entity), so a follow-up run
        reuses the same name/entity for a field it's already seen instead
        of drifting to a different entity assignment — the pipeline's
        (entity, name) dedup key only catches an exact repeat, not a
        reclassified one."""
        ...

    @abstractmethod
    async def extract_rules(self, transcript_text: str) -> List[Rule]:
        ...

    @abstractmethod
    async def extract_fields_from_transcript(
        self, transcript_text: str, existing_fields_context: Optional[str] = None
    ) -> List[FieldCandidate]:
        """A transcript can imply fields no screenshot ever showed — a
        brand-new system discussed purely in conversation has no legacy UI
        to screenshot at all. Independent of extract_fields; the pipeline
        merges both sources and dedupes by (entity, name). See
        `extract_fields` for what `existing_fields_context` is for."""
        ...

    @abstractmethod
    async def generate_stories(
        self, fields: List[FieldCandidate], rules: List[Rule], target_platform: str
    ) -> List[StoryItem]:
        """Draft generation (FR-11), not extraction — turns already-extracted
        fields and rules into an Epic → Feature → Story → Acceptance
        Criteria tree. Every story must trace back to a specific rule."""
        ...

    @abstractmethod
    async def generate_rbp_matrix(
        self,
        fields: List[FieldCandidate],
        rules: List[Rule],
        stories: List[StoryItem],
        target_platform: str,
        existing_grants_context: Optional[str] = None,
    ) -> List[RbpEntry]:
        """Draft generation (Phase 2, RBP drafting) — turns roles mentioned
        in rules/stories into a Create/Read/Update/Delete/Reassign grant per
        role per entity. `existing_grants_context` mirrors
        `existing_fields_context`: role/entity pairs already recorded in a
        prior run, so a follow-up run doesn't re-derive (and potentially
        contradict) a grant that's already there."""
        ...

    @abstractmethod
    async def generate_process_flow(self, transcript_text: str, target_platform: str) -> ProcessFlow:
        """Draft generation, not extraction — maps the CURRENT (as-is)
        process described in the transcript as a sequence of steps and
        transitions, for the Process Flow tab. Distinct from the Story
        Tree, which is the TO-BE system being designed. Generated once per
        project from the full transcript history — the pipeline does not
        attempt to merge new material into an already-generated flow (see
        technical spec section 5)."""
        ...
