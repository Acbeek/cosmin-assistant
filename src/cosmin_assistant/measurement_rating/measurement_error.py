"""Deterministic study-level rating for measurement error."""

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

RULE_NAME_MEASUREMENT_ERROR_PROM = "MPR_MEASUREMENT_ERROR_PROM_V1"
RULE_NAME_MEASUREMENT_ERROR_PBOM = "MPR_MEASUREMENT_ERROR_PBOM_V1"
RULE_NAME_MEASUREMENT_ERROR_ACTIVITY = "MPR_MEASUREMENT_ERROR_ACTIVITY_V1"
RULE_NAME_MEASUREMENT_ERROR_UNSUPPORTED_PROFILE = "MPR_MEASUREMENT_ERROR_UNSUPPORTED_PROFILE_V1"
MEASUREMENT_PROPERTY_MEASUREMENT_ERROR = "measurement_error"

PROFILE_RULE_PREREQUISITE_NAME = "profile_rule_available"
REQUIRED_MIC_PREREQUISITE_NAME = "mic_or_mcid_available"
REQUIRED_NON_PROM_ADAPTATION_PREREQUISITE_NAME = "non_prom_adaptation_equivalence"

_RULE_BY_PROFILE: dict[ProfileType, str] = {
    ProfileType.PROM: RULE_NAME_MEASUREMENT_ERROR_PROM,
    ProfileType.PBOM: RULE_NAME_MEASUREMENT_ERROR_PBOM,
    ProfileType.ACTIVITY_MEASURE: RULE_NAME_MEASUREMENT_ERROR_ACTIVITY,
}


def rate_measurement_error(
    *,
    study_id: StableId,
    instrument_id: StableId,
    statistic_candidates: tuple[StatisticCandidate, ...],
    profile_type: ProfileType | str = ProfileType.PROM,
    prerequisite_decisions: tuple[PrerequisiteDecision, ...] = (),
) -> MeasurementPropertyRatingResult:
    """Rate measurement error with explicit MIC-dependent prerequisites."""

    resolved_profile_type, profile = resolve_profile(profile_type)
    rule_name = _RULE_BY_PROFILE.get(
        resolved_profile_type,
        RULE_NAME_MEASUREMENT_ERROR_UNSUPPORTED_PROFILE,
    )

    relevant = select_statistics(
        statistic_candidates,
        (
            StatisticType.SEM,
            StatisticType.SDC,
            StatisticType.LOA,
            StatisticType.MIC,
        ),
    )
    raw_results = to_raw_result_records(relevant)

    profile_prerequisite = _resolve_profile_prerequisite(
        profile_type=resolved_profile_type,
        profile=profile,
    )
    mic_prerequisite, mic_reference = _resolve_mic_prerequisite(relevant)
    adaptation_prerequisite = _resolve_non_prom_adaptation_prerequisite(
        profile_type=resolved_profile_type,
        decisions=prerequisite_decisions,
    )

    prerequisites = (
        profile_prerequisite,
        mic_prerequisite,
        adaptation_prerequisite,
    )

    if _has_unmet_prerequisites(prerequisites):
        comparisons: tuple[ThresholdComparison, ...] = ()
        rating = MeasurementPropertyRating.INDETERMINATE
        explanation, uncertainty_status = _prerequisite_failure_explanation(prerequisites)
        reviewer_status = ReviewerDecisionStatus.PENDING
    else:
        assert mic_reference is not None
        comparisons = _build_comparisons(relevant, mic_reference)
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
            MEASUREMENT_PROPERTY_MEASUREMENT_ERROR,
            rule_name,
            rating.value,
            ",".join(evidence_span_ids),
        ),
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=MEASUREMENT_PROPERTY_MEASUREMENT_ERROR,
        rule_name=rule_name,
        raw_results=raw_results,
        computed_rating=rating,
        explanation=explanation,
        inputs_used={
            "profile_type": resolved_profile_type.value,
            "statistic_types_considered": [
                StatisticType.SEM.value,
                StatisticType.SDC.value,
                StatisticType.LOA.value,
                StatisticType.MIC.value,
            ],
            "mic_reference_value": mic_reference,
            "mic_reference_strategy": "minimum_numeric_mic",
            "comparison_rules": {
                StatisticType.SEM.value: "SEM <= MIC",
                StatisticType.SDC.value: "SDC <= MIC",
                StatisticType.LOA.value: "max(abs(LoA_lower), abs(LoA_upper)) <= MIC",
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
            detail="No deterministic measurement-error rule is declared for this profile.",
        )

    supports_property = profile.supports_measurement_property(
        MeasurementPropertyKey.MEASUREMENT_ERROR
    )
    if not supports_property:
        return PrerequisiteDecision(
            name=PROFILE_RULE_PREREQUISITE_NAME,
            status=PrerequisiteStatus.NOT_MET,
            detail="Profile does not support measurement error as an auto-scoring property.",
        )

    if not profile.has_deterministic_rule(rule_name):
        return PrerequisiteDecision(
            name=PROFILE_RULE_PREREQUISITE_NAME,
            status=PrerequisiteStatus.NOT_MET,
            detail="Profile lacks the required deterministic measurement-error rule.",
        )

    return PrerequisiteDecision(
        name=PROFILE_RULE_PREREQUISITE_NAME,
        status=PrerequisiteStatus.MET,
        detail="Profile supports deterministic measurement-error scoring.",
    )


def _resolve_mic_prerequisite(
    candidates: tuple[StatisticCandidate, ...],
) -> tuple[PrerequisiteDecision, float | None]:
    mic_candidates = [
        candidate for candidate in candidates if candidate.statistic_type is StatisticType.MIC
    ]
    numeric_values = [
        value
        for candidate in mic_candidates
        for value in [candidate.value_normalized]
        if isinstance(value, float)
    ]

    if not numeric_values:
        return (
            PrerequisiteDecision(
                name=REQUIRED_MIC_PREREQUISITE_NAME,
                status=PrerequisiteStatus.MISSING,
                detail="No numeric MIC/MCID value was available for deterministic comparison.",
                evidence_span_ids=tuple(
                    sorted(
                        {
                            span
                            for candidate in mic_candidates
                            for span in candidate.evidence_span_ids
                        }
                    )
                ),
            ),
            None,
        )

    reference = min(numeric_values)
    evidence_span_ids = tuple(
        sorted({span for candidate in mic_candidates for span in candidate.evidence_span_ids})
    )
    return (
        PrerequisiteDecision(
            name=REQUIRED_MIC_PREREQUISITE_NAME,
            status=PrerequisiteStatus.MET,
            detail="Numeric MIC/MCID evidence was available.",
            evidence_span_ids=evidence_span_ids,
        ),
        reference,
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
            "deterministic thresholds."
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
    messages = [
        f"{decision.name}: {decision.status.value}"
        for decision in prerequisites
        if decision.status in (PrerequisiteStatus.MISSING, PrerequisiteStatus.NOT_MET)
    ]

    if any(decision.name == REQUIRED_MIC_PREREQUISITE_NAME for decision in prerequisites):
        missing_mic = next(
            decision
            for decision in prerequisites
            if decision.name == REQUIRED_MIC_PREREQUISITE_NAME
        )
        if missing_mic.status is PrerequisiteStatus.MISSING:
            return (
                "Measurement error rating is indeterminate because MIC/MCID is missing.",
                UncertaintyStatus.MISSING_EVIDENCE,
            )

    return (
        "Measurement error rating is indeterminate due to unmet prerequisites: "
        + "; ".join(messages),
        UncertaintyStatus.REVIEWER_REQUIRED,
    )


def _build_comparisons(
    candidates: tuple[StatisticCandidate, ...],
    mic_reference: float,
) -> tuple[ThresholdComparison, ...]:
    comparisons: list[ThresholdComparison] = []

    for candidate in candidates:
        if candidate.statistic_type is StatisticType.MIC:
            continue

        value = candidate.value_normalized
        threshold_expression: str
        note: str | None = None

        if candidate.statistic_type is StatisticType.LOA:
            threshold_expression = "max(abs(LoA_lower), abs(LoA_upper)) <= MIC"
            if isinstance(value, tuple) and len(value) == 2:
                magnitude = max(abs(value[0]), abs(value[1]))
                outcome = (
                    ThresholdComparisonOutcome.MEETS
                    if magnitude <= mic_reference
                    else ThresholdComparisonOutcome.FAILS
                )
                note = f"derived_loa_magnitude={magnitude:.6g}; mic_reference={mic_reference:.6g}"
            else:
                outcome = ThresholdComparisonOutcome.NOT_EVALUABLE
                note = "LoA value was not a numeric two-value tuple"
        else:
            threshold_expression = f"{candidate.statistic_type.value.upper()} <= MIC"
            if isinstance(value, float):
                outcome = (
                    ThresholdComparisonOutcome.MEETS
                    if value <= mic_reference
                    else ThresholdComparisonOutcome.FAILS
                )
                note = f"mic_reference={mic_reference:.6g}"
            else:
                outcome = ThresholdComparisonOutcome.NOT_EVALUABLE
                note = "measurement-error value is not numeric"

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
            "No SEM/SDC/LoA statistics were available for measurement-error evaluation.",
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
            "Conflicting measurement-error evidence: some comparisons meet MIC while others fail.",
            UncertaintyStatus.CONFLICTING,
            ReviewerDecisionStatus.PENDING,
        )

    if meets and not fails:
        return (
            MeasurementPropertyRating.SUFFICIENT,
            "All evaluable measurement-error statistics were within MIC/MCID bounds.",
            UncertaintyStatus.CERTAIN,
            ReviewerDecisionStatus.NOT_REQUIRED,
        )

    if fails and not meets:
        return (
            MeasurementPropertyRating.INSUFFICIENT,
            "All evaluable measurement-error statistics exceeded MIC/MCID bounds.",
            UncertaintyStatus.CERTAIN,
            ReviewerDecisionStatus.NOT_REQUIRED,
        )

    return (
        MeasurementPropertyRating.INDETERMINATE,
        "Measurement-error statistics were present but not evaluable against MIC criteria.",
        UncertaintyStatus.AMBIGUOUS,
        ReviewerDecisionStatus.PENDING,
    )
