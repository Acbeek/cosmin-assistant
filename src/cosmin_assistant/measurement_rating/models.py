"""Typed models for deterministic study-level measurement property ratings."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from cosmin_assistant.extract.statistics_models import (
    EvidenceSourceType,
    MeasurementPropertyRoute,
    StatisticType,
)
from cosmin_assistant.models import (
    MeasurementPropertyRating,
    ModelBase,
    NonEmptyText,
    PropertyActivationStatus,
    ReviewerDecisionStatus,
    StableId,
    UncertaintyStatus,
)


class PrerequisiteStatus(StrEnum):
    """Status values for explicit prerequisite checks."""

    MET = "met"
    NOT_MET = "not_met"
    MISSING = "missing"


class ThresholdComparisonOutcome(StrEnum):
    """Outcome of a deterministic threshold comparison."""

    MEETS = "meets"
    FAILS = "fails"
    NOT_EVALUABLE = "not_evaluable"


class PrerequisiteDecision(ModelBase):
    """Explicit prerequisite decision used by rating functions."""

    name: NonEmptyText
    status: PrerequisiteStatus
    detail: str | None = None
    evidence_span_ids: tuple[StableId, ...] = ()


class RawResultRecord(ModelBase):
    """Raw extracted statistic record retained for rating audit trails."""

    statistic_type: StatisticType
    value_raw: NonEmptyText
    value_normalized: float | tuple[float, float] | str | None
    subgroup_label: str | None = None
    evidence_span_ids: tuple[StableId, ...] = Field(min_length=1)
    evidence_source: EvidenceSourceType = EvidenceSourceType.CURRENT_STUDY
    supports_direct_assessment: bool = True
    measurement_property_routes: tuple[MeasurementPropertyRoute, ...] = ()
    instrument_name_hints: tuple[str, ...] = ()
    comparator_instrument_hints: tuple[str, ...] = ()
    provenance_flags: tuple[str, ...] = ()


class ThresholdComparison(ModelBase):
    """One deterministic threshold comparison used in study-level rating."""

    statistic_type: StatisticType
    threshold_expression: NonEmptyText
    observed_value: float | tuple[float, float] | str | None
    outcome: ThresholdComparisonOutcome
    evidence_span_ids: tuple[StableId, ...] = Field(min_length=1)
    note: str | None = None


class MeasurementPropertyRatingResult(ModelBase):
    """Deterministic auditable output of one study-level rating function."""

    id: StableId
    study_id: StableId
    instrument_id: StableId
    measurement_property: NonEmptyText
    rule_name: NonEmptyText
    raw_results: tuple[RawResultRecord, ...]
    computed_rating: MeasurementPropertyRating
    explanation: NonEmptyText
    inputs_used: dict[str, Any]
    prerequisite_decisions: tuple[PrerequisiteDecision, ...] = ()
    threshold_comparisons: tuple[ThresholdComparison, ...] = ()
    evidence_span_ids: tuple[StableId, ...] = ()
    activation_status: PropertyActivationStatus = (
        PropertyActivationStatus.DIRECT_CURRENT_STUDY_EVIDENCE
    )
    uncertainty_status: UncertaintyStatus
    reviewer_decision_status: ReviewerDecisionStatus
