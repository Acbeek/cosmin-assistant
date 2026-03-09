"""Deterministic study-level rating for cross-cultural validity / invariance."""

from __future__ import annotations

from cosmin_assistant.extract.statistics_models import StatisticCandidate, StatisticType
from cosmin_assistant.measurement_rating.common import (
    merge_evidence_span_ids,
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

RULE_NAME_CROSS_CULTURAL_VALIDITY_PROM = "MPR_CROSS_CULTURAL_PROM_V1"
RULE_NAME_CROSS_CULTURAL_VALIDITY_UNSUPPORTED_PROFILE = "MPR_CROSS_CULTURAL_UNSUPPORTED_PROFILE_V1"
MEASUREMENT_PROPERTY_CROSS_CULTURAL_VALIDITY = "cross_cultural_validity_measurement_invariance"
PROFILE_RULE_PREREQUISITE_NAME = "profile_rule_available"


_RULE_BY_PROFILE: dict[ProfileType, str] = {
    ProfileType.PROM: RULE_NAME_CROSS_CULTURAL_VALIDITY_PROM,
}


def rate_cross_cultural_validity_measurement_invariance(
    *,
    study_id: StableId,
    instrument_id: StableId,
    statistic_candidates: tuple[StatisticCandidate, ...],
    profile_type: ProfileType | str = ProfileType.PROM,
) -> MeasurementPropertyRatingResult:
    """Rate cross-cultural validity from measurement-invariance findings."""

    resolved_profile_type, profile = resolve_profile(profile_type)
    profile_prerequisite = _resolve_profile_prerequisite(resolved_profile_type, profile)

    relevant = select_statistics(
        statistic_candidates,
        (StatisticType.MEASUREMENT_INVARIANCE_FINDING,),
    )
    raw_results = to_raw_result_records(relevant)
    comparisons = _build_comparisons(relevant)

    if profile_prerequisite.status is PrerequisiteStatus.MET:
        rule_name = _RULE_BY_PROFILE[resolved_profile_type]
        rating, explanation, uncertainty_status, reviewer_status = _compute_rating(comparisons)
    else:
        rule_name = RULE_NAME_CROSS_CULTURAL_VALIDITY_UNSUPPORTED_PROFILE
        rating = MeasurementPropertyRating.INDETERMINATE
        explanation = (
            "Profile does not provide deterministic cross-cultural validity auto-scoring; "
            "reviewer appraisal is required."
        )
        uncertainty_status = UncertaintyStatus.REVIEWER_REQUIRED
        reviewer_status = ReviewerDecisionStatus.PENDING

    evidence_span_ids = merge_evidence_span_ids(
        raw_results,
        comparisons,
        profile_prerequisite.evidence_span_ids,
    )

    return MeasurementPropertyRatingResult(
        id=stable_id(
            "mpr",
            study_id,
            instrument_id,
            MEASUREMENT_PROPERTY_CROSS_CULTURAL_VALIDITY,
            rule_name,
            rating.value,
            ",".join(evidence_span_ids),
        ),
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=MEASUREMENT_PROPERTY_CROSS_CULTURAL_VALIDITY,
        rule_name=rule_name,
        raw_results=raw_results,
        computed_rating=rating,
        explanation=explanation,
        inputs_used={
            "profile_type": resolved_profile_type.value,
            "profile_rule_prerequisite_status": profile_prerequisite.status.value,
            "statistic_types_considered": [
                StatisticType.MEASUREMENT_INVARIANCE_FINDING.value,
            ],
            "threshold": "measurement_invariance_finding == supported",
            "num_relevant_statistics": len(relevant),
            "num_comparisons": len(comparisons),
        },
        prerequisite_decisions=(profile_prerequisite,),
        threshold_comparisons=comparisons,
        evidence_span_ids=evidence_span_ids,
        uncertainty_status=uncertainty_status,
        reviewer_decision_status=reviewer_status,
    )


def _resolve_profile_prerequisite(
    profile_type: ProfileType,
    profile: BaseProfile,
) -> PrerequisiteDecision:
    rule_name = _RULE_BY_PROFILE.get(profile_type)
    if rule_name is None:
        return PrerequisiteDecision(
            name=PROFILE_RULE_PREREQUISITE_NAME,
            status=PrerequisiteStatus.NOT_MET,
            detail="No deterministic cross-cultural rule is declared for this profile.",
        )

    supports_property = profile.supports_measurement_property(
        MeasurementPropertyKey.CROSS_CULTURAL_VALIDITY_MEASUREMENT_INVARIANCE
    )
    if not supports_property:
        return PrerequisiteDecision(
            name=PROFILE_RULE_PREREQUISITE_NAME,
            status=PrerequisiteStatus.NOT_MET,
            detail="Profile does not support cross-cultural validity as an auto-scoring property.",
        )

    if not profile.has_deterministic_rule(rule_name):
        return PrerequisiteDecision(
            name=PROFILE_RULE_PREREQUISITE_NAME,
            status=PrerequisiteStatus.NOT_MET,
            detail="Profile lacks the required deterministic rule declaration.",
        )

    return PrerequisiteDecision(
        name=PROFILE_RULE_PREREQUISITE_NAME,
        status=PrerequisiteStatus.MET,
        detail="Profile supports deterministic cross-cultural validity scoring.",
    )


def _build_comparisons(
    candidates: tuple[StatisticCandidate, ...],
) -> tuple[ThresholdComparison, ...]:
    comparisons: list[ThresholdComparison] = []

    for candidate in candidates:
        value = candidate.value_normalized
        note: str | None = None

        if value == "supported":
            outcome = ThresholdComparisonOutcome.MEETS
        elif value == "not_supported":
            outcome = ThresholdComparisonOutcome.FAILS
        else:
            outcome = ThresholdComparisonOutcome.NOT_EVALUABLE
            note = "invariance finding was not explicit (expected supported/not_supported)"

        comparisons.append(
            ThresholdComparison(
                statistic_type=candidate.statistic_type,
                threshold_expression="measurement_invariance_finding == supported",
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
            "No measurement-invariance findings were available for cross-cultural validity.",
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
            (
                "Conflicting cross-cultural validity evidence: some invariance findings are "
                "supported while others are not supported."
            ),
            UncertaintyStatus.CONFLICTING,
            ReviewerDecisionStatus.PENDING,
        )

    if meets and not fails:
        return (
            MeasurementPropertyRating.SUFFICIENT,
            "All evaluable measurement-invariance findings were supported.",
            UncertaintyStatus.CERTAIN,
            ReviewerDecisionStatus.NOT_REQUIRED,
        )

    if fails and not meets:
        return (
            MeasurementPropertyRating.INSUFFICIENT,
            "All evaluable measurement-invariance findings were not supported.",
            UncertaintyStatus.CERTAIN,
            ReviewerDecisionStatus.NOT_REQUIRED,
        )

    return (
        MeasurementPropertyRating.INDETERMINATE,
        "Invariance findings were present but not evaluable against deterministic criteria.",
        UncertaintyStatus.AMBIGUOUS,
        ReviewerDecisionStatus.PENDING,
    )
