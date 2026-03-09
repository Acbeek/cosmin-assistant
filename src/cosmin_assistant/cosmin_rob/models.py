"""Typed COSMIN RoB infrastructure models for deterministic box assessments."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from cosmin_assistant.models import (
    CosminBoxAssessment,
    CosminItemAssessment,
    CosminItemRating,
    EvidenceSpanIdList,
    ModelBase,
    NonEmptyText,
    ReviewerDecisionStatus,
    StableId,
    UncertaintyStatus,
)


class BoxItemInput(ModelBase):
    """Input payload for one COSMIN box item rating with explicit evidence links."""

    item_code: NonEmptyText
    item_rating: CosminItemRating
    evidence_span_ids: EvidenceSpanIdList
    uncertainty_status: UncertaintyStatus = UncertaintyStatus.CERTAIN
    reviewer_decision_status: ReviewerDecisionStatus = ReviewerDecisionStatus.NOT_REQUIRED


class BoxAssessmentBundle(ModelBase):
    """Structured output for one assessed COSMIN box.

    This wraps item-level assessments and aggregated box-level results while
    preserving explicit worst-score-counts and NA handling metadata.
    """

    id: StableId
    box_assessment: CosminBoxAssessment
    item_assessments: Annotated[tuple[CosminItemAssessment, ...], Field(min_length=1)]
    aggregation_rule: NonEmptyText
    na_handling_rule: NonEmptyText
    worst_score_counts_applied: bool
    applicable_item_assessment_ids: tuple[StableId, ...]
    not_applicable_item_assessment_ids: tuple[StableId, ...]
    worst_item_assessment_ids: tuple[StableId, ...]
