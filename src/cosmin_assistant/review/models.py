"""Typed models for reviewer override and adjudication flow."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import Field

from cosmin_assistant.models import (
    ModelBase,
    NonEmptyText,
    ReviewerDecisionStatus,
    StableId,
    UncertaintyStatus,
)


class ReviewStatus(StrEnum):
    """Review lifecycle status for exported outputs."""

    PROVISIONAL = "provisional"
    FINALIZED = "finalized"


class OverrideTargetType(StrEnum):
    """Supported derived artifact target types for deterministic overrides."""

    ROB_ITEM_ASSESSMENT = "rob_item_assessment"
    ROB_BOX_ASSESSMENT = "rob_box_assessment"
    MEASUREMENT_PROPERTY_RESULT = "measurement_property_result"
    SYNTHESIS_RESULT = "synthesis_result"
    GRADE_RESULT = "grade_result"


class AdjudicationDecisionKey(StrEnum):
    """Structured reviewer decision keys for manual adjudication steps."""

    TARGET_POPULATION_MATCH = "target_population_match"
    COMPARATOR_SUITABILITY = "comparator_suitability"
    ADEQUACY_OF_HYPOTHESES = "adequacy_of_hypotheses"
    EXPLANATION_OF_INCONSISTENCY = "explanation_of_inconsistency"
    INDIRECTNESS = "indirectness"
    NON_PROM_ADAPTATION_DECISION = "non_prom_adaptation_decision"
    CONTENT_VALIDITY_JUDGMENT = "content_validity_judgment"


class ReviewOverrideRequest(ModelBase):
    """One requested override operation applied to a derived output object."""

    target_object_type: OverrideTargetType
    target_object_id: StableId
    field_name: NonEmptyText
    overridden_value: NonEmptyText
    reason: NonEmptyText
    reviewer_id: StableId
    evidence_span_ids: Annotated[tuple[StableId, ...], Field(min_length=1)]
    decision_status: ReviewerDecisionStatus = ReviewerDecisionStatus.OVERRIDDEN
    created_at_utc: datetime | None = None


class ReviewerAdjudicationNote(ModelBase):
    """Auditable reviewer adjudication note for non-automated decisions."""

    id: StableId
    decision_key: AdjudicationDecisionKey
    decision_value: NonEmptyText
    reason: NonEmptyText
    reviewer_id: StableId
    related_object_type: str | None = None
    related_object_id: StableId | None = None
    evidence_span_ids: Annotated[tuple[StableId, ...], Field(min_length=1)]
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AdjudicationNoteRequest(ModelBase):
    """Input request for appending one adjudication note."""

    decision_key: AdjudicationDecisionKey
    decision_value: NonEmptyText
    reason: NonEmptyText
    reviewer_id: StableId
    related_object_type: str | None = None
    related_object_id: StableId | None = None
    evidence_span_ids: Annotated[tuple[StableId, ...], Field(min_length=1)]
    created_at_utc: datetime | None = None


class ReviewRequestBundle(ModelBase):
    """Batch review request containing overrides and adjudication notes."""

    overrides: tuple[ReviewOverrideRequest, ...] = ()
    adjudication_notes: tuple[AdjudicationNoteRequest, ...] = ()
    finalize: bool = True


class PendingReviewItem(ModelBase):
    """Structured pending-review signal detected from provisional outputs."""

    id: StableId
    source_stage: NonEmptyText
    object_type: NonEmptyText
    object_id: StableId
    reason: NonEmptyText
    evidence_span_ids: tuple[StableId, ...] = ()


class ReviewState(ModelBase):
    """Review lifecycle metadata and audit summary for one output set."""

    id: StableId
    review_status: ReviewStatus
    finalized: bool
    source_output_dir: NonEmptyText
    generated_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    overrides_applied_in_run: int = Field(ge=0)
    overrides_total: int = Field(ge=0)
    adjudication_notes_added_in_run: int = Field(ge=0)
    adjudication_notes_total: int = Field(ge=0)
    pending_review_items: tuple[PendingReviewItem, ...] = ()


def provisional_review_state(*, source_output_dir: str) -> ReviewState:
    """Build default review state for fresh provisional outputs."""

    return ReviewState(
        id="reviewstate.provisional",
        review_status=ReviewStatus.PROVISIONAL,
        finalized=False,
        source_output_dir=source_output_dir,
        overrides_applied_in_run=0,
        overrides_total=0,
        adjudication_notes_added_in_run=0,
        adjudication_notes_total=0,
        pending_review_items=(),
    )


def derive_override_uncertainty() -> UncertaintyStatus:
    """Uncertainty status assigned to applied manual overrides."""

    return UncertaintyStatus.REVIEWER_REQUIRED
