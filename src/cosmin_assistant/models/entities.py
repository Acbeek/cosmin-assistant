"""Core typed Pydantic models for COSMIN appraisal artifacts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import Field, model_validator

from cosmin_assistant.models.base import EvidenceSpanIdList, ModelBase, NonEmptyText, StableId
from cosmin_assistant.models.enums import (
    CosminBoxRating,
    CosminItemRating,
    EvidenceCertaintyLevel,
    MeasurementPropertyRating,
    ProfileType,
    ReviewerDecisionStatus,
    UncertaintyStatus,
)


class ArticleDocument(ModelBase):
    """Parsed article markdown document and metadata."""

    id: StableId
    source_path: NonEmptyText
    markdown_text: NonEmptyText
    metadata: dict[str, Any] = Field(default_factory=dict)


class HeadingSpan(ModelBase):
    """Heading span in an article document."""

    id: StableId
    article_id: StableId
    heading_level: int = Field(ge=1, le=6)
    heading_text: NonEmptyText
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)

    @model_validator(mode="after")
    def _validate_bounds(self) -> HeadingSpan:
        if self.end_char <= self.start_char:
            msg = "end_char must be greater than start_char"
            raise ValueError(msg)
        return self


class EvidenceSpan(ModelBase):
    """Verbatim evidence span used for traceable downstream judgments."""

    id: StableId
    article_id: StableId
    heading_span_id: StableId | None = None
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)
    quoted_text: NonEmptyText

    @model_validator(mode="after")
    def _validate_bounds(self) -> EvidenceSpan:
        if self.end_char <= self.start_char:
            msg = "end_char must be greater than start_char"
            raise ValueError(msg)
        return self


class ExtractedStatistic(ModelBase):
    """Extracted quantitative/statistical datum linked to evidence spans."""

    id: StableId
    article_id: StableId
    study_id: StableId
    instrument_id: StableId
    statistic_name: NonEmptyText
    statistic_value: NonEmptyText
    unit: str | None = None
    evidence_span_ids: EvidenceSpanIdList
    uncertainty_status: UncertaintyStatus


class ExtractedStudyContext(ModelBase):
    """Extracted study-level context linked to evidence spans."""

    id: StableId
    article_id: StableId
    study_id: StableId
    study_design: str | None = None
    population_description: str | None = None
    sample_size: int | None = Field(default=None, ge=0)
    country: str | None = None
    language: str | None = None
    evidence_span_ids: EvidenceSpanIdList
    uncertainty_status: UncertaintyStatus


class ExtractedInstrumentContext(ModelBase):
    """Extracted instrument-level context linked to evidence spans."""

    id: StableId
    article_id: StableId
    study_id: StableId
    instrument_id: StableId
    instrument_name: NonEmptyText
    instrument_version: str | None = None
    subscale: str | None = None
    profile_type: ProfileType
    evidence_span_ids: EvidenceSpanIdList
    uncertainty_status: UncertaintyStatus


class CosminItemAssessment(ModelBase):
    """Item-level COSMIN assessment tied to supporting evidence spans."""

    id: StableId
    study_id: StableId
    instrument_id: StableId
    measurement_property: NonEmptyText
    cosmin_box: NonEmptyText
    item_code: NonEmptyText
    item_rating: CosminItemRating
    evidence_span_ids: EvidenceSpanIdList
    uncertainty_status: UncertaintyStatus
    reviewer_decision_status: ReviewerDecisionStatus


class CosminBoxAssessment(ModelBase):
    """Box-level COSMIN assessment derived from item-level assessments."""

    id: StableId
    study_id: StableId
    instrument_id: StableId
    measurement_property: NonEmptyText
    cosmin_box: NonEmptyText
    box_rating: CosminBoxRating
    item_assessment_ids: Annotated[list[StableId], Field(min_length=1)]
    evidence_span_ids: EvidenceSpanIdList
    uncertainty_status: UncertaintyStatus
    reviewer_decision_status: ReviewerDecisionStatus


class MeasurementPropertyStudyResult(ModelBase):
    """Per-study measurement property result linked to evidence spans."""

    id: StableId
    study_id: StableId
    instrument_id: StableId
    measurement_property: NonEmptyText
    rating: MeasurementPropertyRating
    box_assessment_ids: list[StableId] = Field(default_factory=list)
    evidence_span_ids: EvidenceSpanIdList
    uncertainty_status: UncertaintyStatus
    reviewer_decision_status: ReviewerDecisionStatus


class SynthesisResult(ModelBase):
    """Synthesis result across studies for one instrument and property."""

    id: StableId
    instrument_id: StableId
    measurement_property: NonEmptyText
    study_result_ids: Annotated[list[StableId], Field(min_length=1)]
    rating: MeasurementPropertyRating
    evidence_span_ids: EvidenceSpanIdList
    uncertainty_status: UncertaintyStatus
    reviewer_decision_status: ReviewerDecisionStatus


class GradeDowngradeDecision(ModelBase):
    """One modified-GRADE downgrade decision with explicit traceability."""

    id: StableId
    synthesis_result_id: StableId
    downgrade_domain: NonEmptyText
    downgrade_steps: int = Field(ge=0, le=2)
    certainty_before: EvidenceCertaintyLevel
    certainty_after: EvidenceCertaintyLevel
    evidence_span_ids: EvidenceSpanIdList
    uncertainty_status: UncertaintyStatus
    reviewer_decision_status: ReviewerDecisionStatus


class SummaryOfFindingsRow(ModelBase):
    """Summary-of-findings row for one instrument/property pair."""

    id: StableId
    instrument_id: StableId
    measurement_property: NonEmptyText
    synthesis_result_id: StableId
    final_rating: MeasurementPropertyRating
    evidence_certainty: EvidenceCertaintyLevel
    downgrade_decision_ids: list[StableId] = Field(default_factory=list)
    evidence_span_ids: EvidenceSpanIdList
    uncertainty_status: UncertaintyStatus
    reviewer_decision_status: ReviewerDecisionStatus


class ReviewerOverride(ModelBase):
    """Explicit reviewer override with rationale and evidence references."""

    id: StableId
    target_object_type: NonEmptyText
    target_object_id: StableId
    reviewer_id: StableId
    decision_status: ReviewerDecisionStatus
    reason: NonEmptyText
    previous_value: str | None = None
    overridden_value: str | None = None
    evidence_span_ids: EvidenceSpanIdList
    uncertainty_status: UncertaintyStatus
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
