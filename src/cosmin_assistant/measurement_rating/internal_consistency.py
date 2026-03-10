"""Deterministic study-level rating for internal consistency."""

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
    PrerequisiteDecision,
    PrerequisiteStatus,
    ThresholdComparison,
    ThresholdComparisonOutcome,
)
from cosmin_assistant.models import (
    MeasurementPropertyRating,
    ReviewerDecisionStatus,
    StableId,
    UncertaintyStatus,
)

RULE_NAME_INTERNAL_CONSISTENCY = "MPR_INTERNAL_CONSISTENCY_PROM_V1"
MEASUREMENT_PROPERTY_INTERNAL_CONSISTENCY = "internal_consistency"
REQUIRED_PREREQUISITE_NAME = "structural_validity_sufficient"
_ALPHA_THRESHOLD_EXPRESSION = "0.70 <= alpha <= 0.95"


def rate_internal_consistency(
    *,
    study_id: StableId,
    instrument_id: StableId,
    statistic_candidates: tuple[StatisticCandidate, ...],
    prerequisite_decisions: tuple[PrerequisiteDecision, ...] = (),
) -> MeasurementPropertyRatingResult:
    """Rate internal consistency with explicit prerequisite handling.

    Prerequisite:
    - structural validity sufficiency decision must be explicitly provided as MET.

    Threshold criterion:
    - Cronbach alpha is sufficient when 0.70 <= alpha <= 0.95.
    """

    relevant = select_statistics(
        statistic_candidates,
        (StatisticType.CRONBACH_ALPHA, StatisticType.KR20),
    )
    raw_results = to_raw_result_records(relevant)
    comparisons = _build_comparisons(relevant)
    prerequisite = _resolve_required_prerequisite(prerequisite_decisions)

    rating, explanation, uncertainty_status, reviewer_status = _compute_rating(
        comparisons=comparisons,
        prerequisite=prerequisite,
    )
    prerequisite_spans = prerequisite.evidence_span_ids
    evidence_span_ids = merge_evidence_span_ids(raw_results, comparisons, prerequisite_spans)

    return MeasurementPropertyRatingResult(
        id=stable_id(
            "mpr",
            study_id,
            instrument_id,
            MEASUREMENT_PROPERTY_INTERNAL_CONSISTENCY,
            RULE_NAME_INTERNAL_CONSISTENCY,
            prerequisite.status.value,
            rating.value,
            ",".join(evidence_span_ids),
        ),
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=MEASUREMENT_PROPERTY_INTERNAL_CONSISTENCY,
        rule_name=RULE_NAME_INTERNAL_CONSISTENCY,
        raw_results=raw_results,
        computed_rating=rating,
        explanation=explanation,
        inputs_used={
            "statistic_types_considered": [
                StatisticType.CRONBACH_ALPHA.value,
                StatisticType.KR20.value,
            ],
            "threshold": _ALPHA_THRESHOLD_EXPRESSION,
            "required_prerequisite": REQUIRED_PREREQUISITE_NAME,
            "prerequisite_status": prerequisite.status.value,
            "num_relevant_statistics": len(relevant),
            "num_comparisons": len(comparisons),
        },
        prerequisite_decisions=(prerequisite,),
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
                if 0.70 <= value <= 0.95
                else ThresholdComparisonOutcome.FAILS
            )
            note: str | None = None
        else:
            outcome = ThresholdComparisonOutcome.NOT_EVALUABLE
            note = "normalized alpha/KR-20 statistic is not numeric"

        comparisons.append(
            ThresholdComparison(
                statistic_type=candidate.statistic_type,
                threshold_expression=_ALPHA_THRESHOLD_EXPRESSION,
                observed_value=value,
                outcome=outcome,
                evidence_span_ids=candidate.evidence_span_ids,
                note=note,
            )
        )
    return tuple(comparisons)


def _resolve_required_prerequisite(
    prerequisites: tuple[PrerequisiteDecision, ...],
) -> PrerequisiteDecision:
    matches = [
        decision for decision in prerequisites if decision.name == REQUIRED_PREREQUISITE_NAME
    ]
    if not matches:
        return PrerequisiteDecision(
            name=REQUIRED_PREREQUISITE_NAME,
            status=PrerequisiteStatus.MISSING,
            detail="No explicit structural-validity prerequisite decision was provided.",
        )

    unique_statuses = {decision.status for decision in matches}
    if len(unique_statuses) > 1:
        span_ids = tuple(
            sorted({span_id for decision in matches for span_id in decision.evidence_span_ids})
        )
        return PrerequisiteDecision(
            name=REQUIRED_PREREQUISITE_NAME,
            status=PrerequisiteStatus.MISSING,
            detail="Conflicting prerequisite decisions were provided.",
            evidence_span_ids=span_ids,
        )

    chosen = matches[0]
    return PrerequisiteDecision(
        name=chosen.name,
        status=chosen.status,
        detail=chosen.detail,
        evidence_span_ids=chosen.evidence_span_ids,
    )


def _compute_rating(
    *,
    comparisons: tuple[ThresholdComparison, ...],
    prerequisite: PrerequisiteDecision,
) -> tuple[MeasurementPropertyRating, str, UncertaintyStatus, ReviewerDecisionStatus]:
    if prerequisite.status is PrerequisiteStatus.MISSING:
        return (
            MeasurementPropertyRating.INDETERMINATE,
            (
                "Internal consistency prerequisite is missing: explicit decision on "
                "structural validity sufficiency is required."
            ),
            UncertaintyStatus.MISSING_EVIDENCE,
            ReviewerDecisionStatus.PENDING,
        )

    if prerequisite.status is PrerequisiteStatus.NOT_MET:
        return (
            MeasurementPropertyRating.INDETERMINATE,
            (
                "Internal consistency prerequisite not met: structural validity was not "
                "confirmed as sufficient."
            ),
            UncertaintyStatus.REVIEWER_REQUIRED,
            ReviewerDecisionStatus.PENDING,
        )

    if not comparisons:
        return (
            MeasurementPropertyRating.INDETERMINATE,
            "No alpha/KR-20 statistics were available for internal consistency rating.",
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
            "Conflicting internal-consistency evidence: some alpha values meet and others fail.",
            UncertaintyStatus.CONFLICTING,
            ReviewerDecisionStatus.PENDING,
        )

    if meets and not fails:
        return (
            MeasurementPropertyRating.SUFFICIENT,
            "All evaluable alpha/KR-20 values met deterministic thresholds.",
            UncertaintyStatus.CERTAIN,
            ReviewerDecisionStatus.NOT_REQUIRED,
        )

    if fails and not meets:
        return (
            MeasurementPropertyRating.INSUFFICIENT,
            "All evaluable alpha/KR-20 values failed deterministic thresholds.",
            UncertaintyStatus.CERTAIN,
            ReviewerDecisionStatus.NOT_REQUIRED,
        )

    return (
        MeasurementPropertyRating.INDETERMINATE,
        "Alpha/KR-20 values were present but not evaluable against thresholds.",
        UncertaintyStatus.AMBIGUOUS,
        ReviewerDecisionStatus.PENDING,
    )
