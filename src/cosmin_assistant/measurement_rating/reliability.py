"""Deterministic study-level rating for reliability."""

from __future__ import annotations

from cosmin_assistant.extract.statistics_models import StatisticCandidate, StatisticType
from cosmin_assistant.measurement_rating.common import (
    merge_evidence_span_ids,
    select_statistics,
    stable_id,
    to_raw_result_records,
)
from cosmin_assistant.measurement_rating.models import (
    MeasurementPropertyRatingResult,
    ThresholdComparison,
    ThresholdComparisonOutcome,
)
from cosmin_assistant.models import (
    MeasurementPropertyRating,
    ReviewerDecisionStatus,
    StableId,
    UncertaintyStatus,
)

RULE_NAME_RELIABILITY = "MPR_RELIABILITY_PROM_V1"
MEASUREMENT_PROPERTY_RELIABILITY = "reliability"
_RELIABILITY_THRESHOLD_EXPRESSION = ">= 0.70"


def rate_reliability(
    *,
    study_id: StableId,
    instrument_id: StableId,
    statistic_candidates: tuple[StatisticCandidate, ...],
) -> MeasurementPropertyRatingResult:
    """Rate reliability from ICC and weighted-kappa statistics."""

    relevant = select_statistics(
        statistic_candidates,
        (StatisticType.ICC, StatisticType.WEIGHTED_KAPPA),
    )
    raw_results = to_raw_result_records(relevant)
    comparisons = _build_comparisons(relevant)
    rating, explanation, uncertainty_status, reviewer_status = _compute_rating(comparisons)
    evidence_span_ids = merge_evidence_span_ids(raw_results, comparisons)

    return MeasurementPropertyRatingResult(
        id=stable_id(
            "mpr",
            study_id,
            instrument_id,
            MEASUREMENT_PROPERTY_RELIABILITY,
            RULE_NAME_RELIABILITY,
            rating.value,
            ",".join(evidence_span_ids),
        ),
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=MEASUREMENT_PROPERTY_RELIABILITY,
        rule_name=RULE_NAME_RELIABILITY,
        raw_results=raw_results,
        computed_rating=rating,
        explanation=explanation,
        inputs_used={
            "statistic_types_considered": [
                StatisticType.ICC.value,
                StatisticType.WEIGHTED_KAPPA.value,
            ],
            "threshold": _RELIABILITY_THRESHOLD_EXPRESSION,
            "num_relevant_statistics": len(relevant),
            "num_comparisons": len(comparisons),
        },
        threshold_comparisons=comparisons,
        evidence_span_ids=evidence_span_ids,
        uncertainty_status=uncertainty_status,
        reviewer_decision_status=reviewer_status,
    )


def _build_comparisons(
    candidates: tuple[StatisticCandidate, ...],
) -> tuple[ThresholdComparison, ...]:
    comparisons: list[ThresholdComparison] = []
    for candidate in candidates:
        value = candidate.value_normalized
        if isinstance(value, float):
            outcome = (
                ThresholdComparisonOutcome.MEETS
                if value >= 0.70
                else ThresholdComparisonOutcome.FAILS
            )
            note: str | None = None
        else:
            outcome = ThresholdComparisonOutcome.NOT_EVALUABLE
            note = "normalized reliability statistic is not numeric"

        comparisons.append(
            ThresholdComparison(
                statistic_type=candidate.statistic_type,
                threshold_expression=_RELIABILITY_THRESHOLD_EXPRESSION,
                observed_value=value,
                outcome=outcome,
                evidence_span_ids=candidate.evidence_span_ids,
                note=note,
            )
        )
    return tuple(comparisons)


def _compute_rating(
    comparisons: tuple[ThresholdComparison, ...],
) -> tuple[MeasurementPropertyRating, str, UncertaintyStatus, ReviewerDecisionStatus]:
    if not comparisons:
        return (
            MeasurementPropertyRating.INDETERMINATE,
            "No ICC or weighted-kappa statistics were available for reliability rating.",
            UncertaintyStatus.MISSING_EVIDENCE,
            ReviewerDecisionStatus.PENDING,
        )

    meets = [
        comparison
        for comparison in comparisons
        if comparison.outcome is ThresholdComparisonOutcome.MEETS
    ]
    fails = [
        comparison
        for comparison in comparisons
        if comparison.outcome is ThresholdComparisonOutcome.FAILS
    ]

    if meets and fails:
        return (
            MeasurementPropertyRating.INCONSISTENT,
            "Conflicting reliability evidence: some coefficients meet and others fail.",
            UncertaintyStatus.CONFLICTING,
            ReviewerDecisionStatus.PENDING,
        )

    if meets and not fails:
        return (
            MeasurementPropertyRating.SUFFICIENT,
            "All evaluable reliability coefficients met deterministic thresholds.",
            UncertaintyStatus.CERTAIN,
            ReviewerDecisionStatus.NOT_REQUIRED,
        )

    if fails and not meets:
        return (
            MeasurementPropertyRating.INSUFFICIENT,
            "All evaluable reliability coefficients failed deterministic thresholds.",
            UncertaintyStatus.CERTAIN,
            ReviewerDecisionStatus.NOT_REQUIRED,
        )

    return (
        MeasurementPropertyRating.INDETERMINATE,
        "Reliability statistics were present but not evaluable against thresholds.",
        UncertaintyStatus.AMBIGUOUS,
        ReviewerDecisionStatus.PENDING,
    )
