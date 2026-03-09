"""Deterministic study-level rating for responsiveness."""

from __future__ import annotations

from cosmin_assistant.extract.statistics_models import StatisticCandidate, StatisticType
from cosmin_assistant.measurement_rating.common import (
    merge_evidence_span_ids,
    resolve_named_prerequisite,
    resolve_profile,
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
    ProfileType,
    ReviewerDecisionStatus,
    StableId,
    UncertaintyStatus,
)
from cosmin_assistant.profiles.base import BaseProfile
from cosmin_assistant.profiles.constants import MeasurementPropertyKey

RULE_NAME_RESPONSIVENESS_PROM = "MPR_RESPONSIVENESS_PROM_V1"
RULE_NAME_RESPONSIVENESS_PBOM = "MPR_RESPONSIVENESS_PBOM_V1"
RULE_NAME_RESPONSIVENESS_ACTIVITY = "MPR_RESPONSIVENESS_ACTIVITY_V1"
RULE_NAME_RESPONSIVENESS_UNSUPPORTED_PROFILE = "MPR_RESPONSIVENESS_UNSUPPORTED_PROFILE_V1"
MEASUREMENT_PROPERTY_RESPONSIVENESS = "responsiveness"

PROFILE_RULE_PREREQUISITE_NAME = "profile_rule_available"
REQUIRED_HYPOTHESES_PREREQUISITE_NAME = "predefined_hypotheses_available"
REQUIRED_NON_PROM_ADAPTATION_PREREQUISITE_NAME = "non_prom_adaptation_equivalence"

_RULE_BY_PROFILE: dict[ProfileType, str] = {
    ProfileType.PROM: RULE_NAME_RESPONSIVENESS_PROM,
    ProfileType.PBOM: RULE_NAME_RESPONSIVENESS_PBOM,
    ProfileType.ACTIVITY_MEASURE: RULE_NAME_RESPONSIVENESS_ACTIVITY,
}
_RESPONSIVENESS_THRESHOLD_BY_PROFILE: dict[ProfileType, float] = {
    ProfileType.PROM: 0.50,
    ProfileType.PBOM: 0.50,
    ProfileType.ACTIVITY_MEASURE: 0.50,
}


def rate_responsiveness(
    *,
    study_id: StableId,
    instrument_id: StableId,
    statistic_candidates: tuple[StatisticCandidate, ...],
    prerequisite_decisions: tuple[PrerequisiteDecision, ...] = (),
    profile_type: ProfileType | str = ProfileType.PROM,
) -> MeasurementPropertyRatingResult:
    """Rate responsiveness with explicit hypothesis prerequisite handling."""

    resolved_profile_type, profile = resolve_profile(profile_type)
    rule_name = _RULE_BY_PROFILE.get(
        resolved_profile_type,
        RULE_NAME_RESPONSIVENESS_UNSUPPORTED_PROFILE,
    )

    relevant = select_statistics(
        statistic_candidates,
        (StatisticType.RESPONSIVENESS_RELATED_STATISTIC, StatisticType.AUC),
    )
    raw_results = to_raw_result_records(relevant)

    profile_prerequisite = _resolve_profile_prerequisite(
        profile_type=resolved_profile_type,
        profile=profile,
    )
    hypotheses_prerequisite = resolve_named_prerequisite(
        decisions=prerequisite_decisions,
        name=REQUIRED_HYPOTHESES_PREREQUISITE_NAME,
        missing_detail="Predefined hypotheses are required for responsiveness scoring.",
    )
    adaptation_prerequisite = _resolve_non_prom_adaptation_prerequisite(
        profile_type=resolved_profile_type,
        decisions=prerequisite_decisions,
    )
    prerequisites = (
        profile_prerequisite,
        hypotheses_prerequisite,
        adaptation_prerequisite,
    )

    if _has_unmet_prerequisites(prerequisites):
        comparisons: tuple[ThresholdComparison, ...] = ()
        rating = MeasurementPropertyRating.INDETERMINATE
        explanation, uncertainty_status = _prerequisite_failure_explanation(prerequisites)
        reviewer_status = ReviewerDecisionStatus.PENDING
    else:
        threshold = _RESPONSIVENESS_THRESHOLD_BY_PROFILE[resolved_profile_type]
        comparisons = _build_comparisons(relevant, threshold)
        rating, explanation, uncertainty_status, reviewer_status = _compute_rating(comparisons)

    evidence_span_ids = merge_evidence_span_ids(
        raw_results,
        comparisons,
        [span for decision in prerequisites for span in decision.evidence_span_ids],
    )

    return MeasurementPropertyRatingResult(
        id=stable_id(
            "mpr",
            study_id,
            instrument_id,
            MEASUREMENT_PROPERTY_RESPONSIVENESS,
            rule_name,
            rating.value,
            ",".join(evidence_span_ids),
        ),
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=MEASUREMENT_PROPERTY_RESPONSIVENESS,
        rule_name=rule_name,
        raw_results=raw_results,
        computed_rating=rating,
        explanation=explanation,
        inputs_used={
            "profile_type": resolved_profile_type.value,
            "statistic_types_considered": [
                StatisticType.RESPONSIVENESS_RELATED_STATISTIC.value,
                StatisticType.AUC.value,
            ],
            "thresholds": {
                StatisticType.RESPONSIVENESS_RELATED_STATISTIC.value: (
                    f">= {_RESPONSIVENESS_THRESHOLD_BY_PROFILE.get(resolved_profile_type)}"
                ),
                StatisticType.AUC.value: ">= 0.70",
            },
            "num_relevant_statistics": len(relevant),
            "num_comparisons": len(comparisons),
            "prerequisite_statuses": {
                decision.name: decision.status.value for decision in prerequisites
            },
        },
        prerequisite_decisions=prerequisites,
        threshold_comparisons=comparisons,
        evidence_span_ids=evidence_span_ids,
        uncertainty_status=uncertainty_status,
        reviewer_decision_status=reviewer_status,
    )


def _resolve_profile_prerequisite(
    *,
    profile_type: ProfileType,
    profile: BaseProfile,
) -> PrerequisiteDecision:
    rule_name = _RULE_BY_PROFILE.get(profile_type)
    if rule_name is None:
        return PrerequisiteDecision(
            name=PROFILE_RULE_PREREQUISITE_NAME,
            status=PrerequisiteStatus.NOT_MET,
            detail="No deterministic responsiveness rule is declared for this profile.",
        )

    supports_property = profile.supports_measurement_property(MeasurementPropertyKey.RESPONSIVENESS)
    if not supports_property:
        return PrerequisiteDecision(
            name=PROFILE_RULE_PREREQUISITE_NAME,
            status=PrerequisiteStatus.NOT_MET,
            detail="Profile does not support responsiveness auto-scoring.",
        )

    if not profile.has_deterministic_rule(rule_name):
        return PrerequisiteDecision(
            name=PROFILE_RULE_PREREQUISITE_NAME,
            status=PrerequisiteStatus.NOT_MET,
            detail="Profile lacks the required deterministic responsiveness rule.",
        )

    return PrerequisiteDecision(
        name=PROFILE_RULE_PREREQUISITE_NAME,
        status=PrerequisiteStatus.MET,
        detail="Profile supports deterministic responsiveness scoring.",
    )


def _resolve_non_prom_adaptation_prerequisite(
    *,
    profile_type: ProfileType,
    decisions: tuple[PrerequisiteDecision, ...],
) -> PrerequisiteDecision:
    if profile_type is ProfileType.PROM:
        return PrerequisiteDecision(
            name=REQUIRED_NON_PROM_ADAPTATION_PREREQUISITE_NAME,
            status=PrerequisiteStatus.MET,
            detail="PROM reference profile does not require non-PROM adaptation confirmation.",
        )

    return resolve_named_prerequisite(
        decisions=decisions,
        name=REQUIRED_NON_PROM_ADAPTATION_PREREQUISITE_NAME,
        missing_detail=(
            "Non-PROM adaptation equivalence decision is required before applying "
            "responsiveness thresholds."
        ),
    )


def _has_unmet_prerequisites(prerequisites: tuple[PrerequisiteDecision, ...]) -> bool:
    return any(
        decision.status in (PrerequisiteStatus.MISSING, PrerequisiteStatus.NOT_MET)
        for decision in prerequisites
    )


def _prerequisite_failure_explanation(
    prerequisites: tuple[PrerequisiteDecision, ...],
) -> tuple[str, UncertaintyStatus]:
    hypotheses = next(
        decision
        for decision in prerequisites
        if decision.name == REQUIRED_HYPOTHESES_PREREQUISITE_NAME
    )
    if hypotheses.status is PrerequisiteStatus.MISSING:
        return (
            "Responsiveness is indeterminate because predefined hypotheses are missing.",
            UncertaintyStatus.MISSING_EVIDENCE,
        )

    return (
        "Responsiveness is indeterminate due to unmet prerequisites.",
        UncertaintyStatus.REVIEWER_REQUIRED,
    )


def _build_comparisons(
    candidates: tuple[StatisticCandidate, ...],
    threshold: float,
) -> tuple[ThresholdComparison, ...]:
    comparisons: list[ThresholdComparison] = []

    for candidate in candidates:
        value = candidate.value_normalized
        note: str | None = None

        if candidate.statistic_type is StatisticType.RESPONSIVENESS_RELATED_STATISTIC:
            threshold_expression = f"responsiveness_statistic >= {threshold:.2f}"
            if isinstance(value, float):
                outcome = (
                    ThresholdComparisonOutcome.MEETS
                    if value >= threshold
                    else ThresholdComparisonOutcome.FAILS
                )
            else:
                outcome = ThresholdComparisonOutcome.NOT_EVALUABLE
                note = "responsiveness statistic was non-numeric"
        else:
            threshold_expression = "AUC >= 0.70"
            if isinstance(value, float):
                outcome = (
                    ThresholdComparisonOutcome.MEETS
                    if value >= 0.70
                    else ThresholdComparisonOutcome.FAILS
                )
            else:
                outcome = ThresholdComparisonOutcome.NOT_EVALUABLE
                note = "AUC value is not numeric"

        comparisons.append(
            ThresholdComparison(
                statistic_type=candidate.statistic_type,
                threshold_expression=threshold_expression,
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
            "No responsiveness statistics were available.",
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
            "Conflicting responsiveness evidence: some statistics meet and others fail.",
            UncertaintyStatus.CONFLICTING,
            ReviewerDecisionStatus.PENDING,
        )

    if meets and not fails:
        return (
            MeasurementPropertyRating.SUFFICIENT,
            "All evaluable responsiveness statistics met deterministic thresholds.",
            UncertaintyStatus.CERTAIN,
            ReviewerDecisionStatus.NOT_REQUIRED,
        )

    if fails and not meets:
        return (
            MeasurementPropertyRating.INSUFFICIENT,
            "All evaluable responsiveness statistics failed deterministic thresholds.",
            UncertaintyStatus.CERTAIN,
            ReviewerDecisionStatus.NOT_REQUIRED,
        )

    return (
        MeasurementPropertyRating.INDETERMINATE,
        "Responsiveness evidence was present but not evaluable.",
        UncertaintyStatus.AMBIGUOUS,
        ReviewerDecisionStatus.PENDING,
    )
