"""Typed models for first-pass synthesis across studies."""

from __future__ import annotations

from pydantic import Field

from cosmin_assistant.models import (
    MeasurementPropertyRating,
    ModelBase,
    NonEmptyText,
    PropertyActivationStatus,
    ReviewerDecisionStatus,
    StableId,
)


class StudySynthesisInput(ModelBase):
    """Study-level input record used for first-pass synthesis."""

    id: StableId
    study_id: StableId
    instrument_name: NonEmptyText
    instrument_version: str | None = None
    subscale: str | None = None
    measurement_property: NonEmptyText
    rating: MeasurementPropertyRating
    sample_size: int | None = Field(default=None, ge=0)
    evidence_span_ids: tuple[StableId, ...] = Field(min_length=1)
    subgroup_label: str | None = None
    study_explanation: str | None = None
    activation_status: PropertyActivationStatus = (
        PropertyActivationStatus.DIRECT_CURRENT_STUDY_EVIDENCE
    )


class SubgroupExplanationPlaceholder(ModelBase):
    """Placeholder object for reviewer-provided subgroup explanations."""

    subgroup_label: NonEmptyText
    explanation_status: ReviewerDecisionStatus = ReviewerDecisionStatus.PENDING
    explanation_text: str | None = None
    evidence_span_ids: tuple[StableId, ...] = ()


class SynthesisAggregateResult(ModelBase):
    """Aggregated synthesis result preserving study-level records."""

    id: StableId
    instrument_name: NonEmptyText
    instrument_version: str | None = None
    subscale: str | None = None
    measurement_property: NonEmptyText
    summary_rating: MeasurementPropertyRating
    summary_explanation: NonEmptyText
    inconsistent_findings: bool
    requires_subgroup_explanation: bool
    total_sample_size: int | None = Field(default=None, ge=0)
    study_entries: tuple[StudySynthesisInput, ...] = Field(min_length=1)
    subgroup_explanation_placeholders: tuple[SubgroupExplanationPlaceholder, ...] = ()
    evidence_span_ids: tuple[StableId, ...] = Field(min_length=1)
    activation_status: PropertyActivationStatus = (
        PropertyActivationStatus.DIRECT_CURRENT_STUDY_EVIDENCE
    )
