"""Deterministic study-level rating for structural validity."""

from __future__ import annotations

from collections.abc import Callable

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

RULE_NAME_STRUCTURAL_VALIDITY = "MPR_STRUCTURAL_VALIDITY_PROM_V1"
MEASUREMENT_PROPERTY_STRUCTURAL_VALIDITY = "structural_validity"

_THRESHOLDS: dict[StatisticType, tuple[str, Callable[[float], bool]]] = {
    StatisticType.CFI: (">= 0.95", lambda value: value >= 0.95),
    StatisticType.TLI: (">= 0.95", lambda value: value >= 0.95),
    StatisticType.RMSEA: ("<= 0.06", lambda value: value <= 0.06),
    StatisticType.SRMR: ("<= 0.08", lambda value: value <= 0.08),
}


def rate_structural_validity(
    *,
    study_id: StableId,
    instrument_id: StableId,
    statistic_candidates: tuple[StatisticCandidate, ...],
) -> MeasurementPropertyRatingResult:
    """Rate structural validity with deterministic threshold comparisons.

    Threshold criteria:
    - CFI/TLI: sufficient signal when value >= 0.95
    - RMSEA/SRMR: sufficient signal when value <= threshold
    """

    relevant = select_statistics(statistic_candidates, tuple(_THRESHOLDS))
    raw_results = to_raw_result_records(relevant)
    comparisons = _build_comparisons(relevant)

    rating, explanation, uncertainty_status, reviewer_status = _compute_rating(comparisons)
    evidence_span_ids = merge_evidence_span_ids(raw_results, comparisons)

    return MeasurementPropertyRatingResult(
        id=stable_id(
            "mpr",
            study_id,
            instrument_id,
            MEASUREMENT_PROPERTY_STRUCTURAL_VALIDITY,
            RULE_NAME_STRUCTURAL_VALIDITY,
            rating.value,
            ",".join(evidence_span_ids),
        ),
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=MEASUREMENT_PROPERTY_STRUCTURAL_VALIDITY,
        rule_name=RULE_NAME_STRUCTURAL_VALIDITY,
        raw_results=raw_results,
        computed_rating=rating,
        explanation=explanation,
        inputs_used={
            "statistic_types_considered": [stat.value for stat in _THRESHOLDS],
            "thresholds": {stat.value: expression for stat, (expression, _) in _THRESHOLDS.items()},
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
        expression, comparator = _THRESHOLDS[candidate.statistic_type]
        value = candidate.value_normalized

        if isinstance(value, float):
            outcome = (
                ThresholdComparisonOutcome.MEETS
                if comparator(value)
                else ThresholdComparisonOutcome.FAILS
            )
            note: str | None = None
        else:
            outcome = ThresholdComparisonOutcome.NOT_EVALUABLE
            note = "normalized statistic value is not numeric"

        comparisons.append(
            ThresholdComparison(
                statistic_type=candidate.statistic_type,
                threshold_expression=expression,
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
            "No structural-validity statistics (CFI/TLI/RMSEA/SRMR) were available.",
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
    not_evaluable = [
        comparison
        for comparison in comparisons
        if comparison.outcome is ThresholdComparisonOutcome.NOT_EVALUABLE
    ]

    if meets and fails:
        return (
            MeasurementPropertyRating.INCONSISTENT,
            (
                "Conflicting structural-validity evidence: some statistics meet thresholds "
                "while others fail."
            ),
            UncertaintyStatus.CONFLICTING,
            ReviewerDecisionStatus.PENDING,
        )

    if meets and not fails:
        return (
            MeasurementPropertyRating.SUFFICIENT,
            "All evaluable structural-validity statistics met deterministic thresholds.",
            UncertaintyStatus.CERTAIN,
            ReviewerDecisionStatus.NOT_REQUIRED,
        )

    if fails and not meets:
        return (
            MeasurementPropertyRating.INSUFFICIENT,
            "All evaluable structural-validity statistics failed deterministic thresholds.",
            UncertaintyStatus.CERTAIN,
            ReviewerDecisionStatus.NOT_REQUIRED,
        )

    return (
        MeasurementPropertyRating.INDETERMINATE,
        (
            "Structural-validity statistics were present but not evaluable against thresholds "
            f"({len(not_evaluable)} non-numeric values)."
        ),
        UncertaintyStatus.AMBIGUOUS,
        ReviewerDecisionStatus.PENDING,
    )
