"""Tests for remaining deterministic study-level measurement-property ratings."""

from __future__ import annotations

from cosmin_assistant.extract import StatisticCandidate, StatisticType
from cosmin_assistant.measurement_rating import (
    REQUIRED_GOLD_STANDARD_PREREQUISITE_NAME,
    REQUIRED_HYPOTHESES_PREREQUISITE_NAME,
    REQUIRED_MIC_PREREQUISITE_NAME,
    REQUIRED_NON_PROM_ADAPTATION_PREREQUISITE_NAME,
    PrerequisiteDecision,
    PrerequisiteStatus,
    rate_criterion_validity,
    rate_cross_cultural_validity_measurement_invariance,
    rate_hypotheses_testing_for_construct_validity,
    rate_measurement_error,
    rate_responsiveness,
)
from cosmin_assistant.models import (
    MeasurementPropertyRating,
    ReviewerDecisionStatus,
    UncertaintyStatus,
)


def _candidate(
    *,
    candidate_id: str,
    statistic_type: StatisticType,
    value_raw: str,
    value_normalized: float | tuple[float, float] | str | None,
    evidence_span_id: str,
) -> StatisticCandidate:
    return StatisticCandidate(
        id=candidate_id,
        statistic_type=statistic_type,
        value_raw=value_raw,
        value_normalized=value_normalized,
        evidence_span_ids=(evidence_span_id,),
        surrounding_text=f"{statistic_type.value}={value_raw}",
    )


def test_cross_cultural_validity_sufficient_and_conflicting_paths() -> None:
    sufficient = rate_cross_cultural_validity_measurement_invariance(
        study_id="study.501",
        instrument_id="inst.501",
        statistic_candidates=(
            _candidate(
                candidate_id="stat.501",
                statistic_type=StatisticType.MEASUREMENT_INVARIANCE_FINDING,
                value_raw="supported",
                value_normalized="supported",
                evidence_span_id="sen.501",
            ),
        ),
    )
    conflicting = rate_cross_cultural_validity_measurement_invariance(
        study_id="study.502",
        instrument_id="inst.502",
        statistic_candidates=(
            _candidate(
                candidate_id="stat.502",
                statistic_type=StatisticType.MEASUREMENT_INVARIANCE_FINDING,
                value_raw="supported",
                value_normalized="supported",
                evidence_span_id="sen.502",
            ),
            _candidate(
                candidate_id="stat.503",
                statistic_type=StatisticType.MEASUREMENT_INVARIANCE_FINDING,
                value_raw="not supported",
                value_normalized="not_supported",
                evidence_span_id="sen.503",
            ),
        ),
    )

    assert sufficient.computed_rating is MeasurementPropertyRating.SUFFICIENT
    assert sufficient.rule_name == "MPR_CROSS_CULTURAL_PROM_V1"
    assert set(sufficient.evidence_span_ids) == {"sen.501"}

    assert conflicting.computed_rating is MeasurementPropertyRating.INCONSISTENT
    assert conflicting.uncertainty_status is UncertaintyStatus.CONFLICTING
    assert conflicting.reviewer_decision_status is ReviewerDecisionStatus.PENDING


def test_cross_cultural_validity_non_prom_profile_is_indeterminate_reviewer_required() -> None:
    result = rate_cross_cultural_validity_measurement_invariance(
        study_id="study.503",
        instrument_id="inst.503",
        profile_type="pbom",
        statistic_candidates=(
            _candidate(
                candidate_id="stat.504",
                statistic_type=StatisticType.MEASUREMENT_INVARIANCE_FINDING,
                value_raw="supported",
                value_normalized="supported",
                evidence_span_id="sen.504",
            ),
        ),
    )

    assert result.computed_rating is MeasurementPropertyRating.INDETERMINATE
    assert result.prerequisite_decisions[0].status is PrerequisiteStatus.NOT_MET
    assert result.uncertainty_status is UncertaintyStatus.REVIEWER_REQUIRED


def test_measurement_error_sufficient_insufficient_conflicting_and_missing_mic() -> None:
    sufficient = rate_measurement_error(
        study_id="study.601",
        instrument_id="inst.601",
        statistic_candidates=(
            _candidate(
                candidate_id="stat.601",
                statistic_type=StatisticType.MIC,
                value_raw="5.0",
                value_normalized=5.0,
                evidence_span_id="sen.601",
            ),
            _candidate(
                candidate_id="stat.602",
                statistic_type=StatisticType.SDC,
                value_raw="4.1",
                value_normalized=4.1,
                evidence_span_id="sen.602",
            ),
        ),
    )
    insufficient = rate_measurement_error(
        study_id="study.602",
        instrument_id="inst.602",
        statistic_candidates=(
            _candidate(
                candidate_id="stat.603",
                statistic_type=StatisticType.MIC,
                value_raw="3.0",
                value_normalized=3.0,
                evidence_span_id="sen.603",
            ),
            _candidate(
                candidate_id="stat.604",
                statistic_type=StatisticType.SEM,
                value_raw="4.2",
                value_normalized=4.2,
                evidence_span_id="sen.604",
            ),
        ),
    )
    conflicting = rate_measurement_error(
        study_id="study.603",
        instrument_id="inst.603",
        statistic_candidates=(
            _candidate(
                candidate_id="stat.605",
                statistic_type=StatisticType.MIC,
                value_raw="5.0",
                value_normalized=5.0,
                evidence_span_id="sen.605",
            ),
            _candidate(
                candidate_id="stat.606",
                statistic_type=StatisticType.SEM,
                value_raw="3.5",
                value_normalized=3.5,
                evidence_span_id="sen.606",
            ),
            _candidate(
                candidate_id="stat.607",
                statistic_type=StatisticType.SDC,
                value_raw="6.1",
                value_normalized=6.1,
                evidence_span_id="sen.607",
            ),
        ),
    )
    missing_mic = rate_measurement_error(
        study_id="study.604",
        instrument_id="inst.604",
        statistic_candidates=(
            _candidate(
                candidate_id="stat.608",
                statistic_type=StatisticType.SEM,
                value_raw="2.1",
                value_normalized=2.1,
                evidence_span_id="sen.608",
            ),
        ),
    )

    assert sufficient.computed_rating is MeasurementPropertyRating.SUFFICIENT
    assert insufficient.computed_rating is MeasurementPropertyRating.INSUFFICIENT
    assert conflicting.computed_rating is MeasurementPropertyRating.INCONSISTENT
    assert conflicting.uncertainty_status is UncertaintyStatus.CONFLICTING

    assert missing_mic.computed_rating is MeasurementPropertyRating.INDETERMINATE
    mic_prerequisite = next(
        decision
        for decision in missing_mic.prerequisite_decisions
        if decision.name == REQUIRED_MIC_PREREQUISITE_NAME
    )
    assert mic_prerequisite.status is PrerequisiteStatus.MISSING
    assert missing_mic.uncertainty_status is UncertaintyStatus.MISSING_EVIDENCE


def test_measurement_error_non_prom_requires_adaptation_prerequisite() -> None:
    result = rate_measurement_error(
        study_id="study.605",
        instrument_id="inst.605",
        profile_type="activity_measure",
        statistic_candidates=(
            _candidate(
                candidate_id="stat.609",
                statistic_type=StatisticType.MIC,
                value_raw="5.0",
                value_normalized=5.0,
                evidence_span_id="sen.609",
            ),
            _candidate(
                candidate_id="stat.610",
                statistic_type=StatisticType.SDC,
                value_raw="4.0",
                value_normalized=4.0,
                evidence_span_id="sen.610",
            ),
        ),
    )

    assert result.computed_rating is MeasurementPropertyRating.INDETERMINATE
    adaptation = next(
        decision
        for decision in result.prerequisite_decisions
        if decision.name == REQUIRED_NON_PROM_ADAPTATION_PREREQUISITE_NAME
    )
    assert adaptation.status is PrerequisiteStatus.MISSING
    assert result.uncertainty_status is UncertaintyStatus.REVIEWER_REQUIRED


def test_criterion_validity_sufficient_insufficient_and_missing_prerequisite() -> None:
    sufficient = rate_criterion_validity(
        study_id="study.701",
        instrument_id="inst.701",
        prerequisite_decisions=(
            PrerequisiteDecision(
                name=REQUIRED_GOLD_STANDARD_PREREQUISITE_NAME,
                status=PrerequisiteStatus.MET,
                evidence_span_ids=("sen.701p",),
            ),
        ),
        statistic_candidates=(
            _candidate(
                candidate_id="stat.701",
                statistic_type=StatisticType.CORRELATION,
                value_raw="0.82",
                value_normalized=0.82,
                evidence_span_id="sen.701",
            ),
        ),
    )
    insufficient = rate_criterion_validity(
        study_id="study.702",
        instrument_id="inst.702",
        prerequisite_decisions=(
            PrerequisiteDecision(
                name=REQUIRED_GOLD_STANDARD_PREREQUISITE_NAME,
                status=PrerequisiteStatus.MET,
                evidence_span_ids=("sen.702p",),
            ),
        ),
        statistic_candidates=(
            _candidate(
                candidate_id="stat.702",
                statistic_type=StatisticType.AUC,
                value_raw="0.62",
                value_normalized=0.62,
                evidence_span_id="sen.702",
            ),
        ),
    )
    missing = rate_criterion_validity(
        study_id="study.703",
        instrument_id="inst.703",
        statistic_candidates=(
            _candidate(
                candidate_id="stat.703",
                statistic_type=StatisticType.CORRELATION,
                value_raw="0.82",
                value_normalized=0.82,
                evidence_span_id="sen.703",
            ),
        ),
    )

    assert sufficient.computed_rating is MeasurementPropertyRating.SUFFICIENT
    assert insufficient.computed_rating is MeasurementPropertyRating.INSUFFICIENT

    assert missing.computed_rating is MeasurementPropertyRating.INDETERMINATE
    assert missing.uncertainty_status is UncertaintyStatus.MISSING_EVIDENCE


def test_criterion_validity_conflicting_and_profile_unsupported_paths() -> None:
    conflicting = rate_criterion_validity(
        study_id="study.704",
        instrument_id="inst.704",
        prerequisite_decisions=(
            PrerequisiteDecision(
                name=REQUIRED_GOLD_STANDARD_PREREQUISITE_NAME,
                status=PrerequisiteStatus.MET,
            ),
        ),
        statistic_candidates=(
            _candidate(
                candidate_id="stat.704",
                statistic_type=StatisticType.CORRELATION,
                value_raw="0.84",
                value_normalized=0.84,
                evidence_span_id="sen.704",
            ),
            _candidate(
                candidate_id="stat.705",
                statistic_type=StatisticType.AUC,
                value_raw="0.61",
                value_normalized=0.61,
                evidence_span_id="sen.705",
            ),
        ),
    )
    unsupported = rate_criterion_validity(
        study_id="study.705",
        instrument_id="inst.705",
        profile_type="pbom",
        prerequisite_decisions=(
            PrerequisiteDecision(
                name=REQUIRED_GOLD_STANDARD_PREREQUISITE_NAME,
                status=PrerequisiteStatus.MET,
            ),
        ),
        statistic_candidates=(
            _candidate(
                candidate_id="stat.706",
                statistic_type=StatisticType.CORRELATION,
                value_raw="0.90",
                value_normalized=0.90,
                evidence_span_id="sen.706",
            ),
        ),
    )

    assert conflicting.computed_rating is MeasurementPropertyRating.INCONSISTENT
    assert unsupported.computed_rating is MeasurementPropertyRating.INDETERMINATE
    assert unsupported.uncertainty_status is UncertaintyStatus.REVIEWER_REQUIRED


def test_construct_validity_paths_and_prerequisites() -> None:
    sufficient = rate_hypotheses_testing_for_construct_validity(
        study_id="study.801",
        instrument_id="inst.801",
        prerequisite_decisions=(
            PrerequisiteDecision(
                name=REQUIRED_HYPOTHESES_PREREQUISITE_NAME,
                status=PrerequisiteStatus.MET,
            ),
        ),
        statistic_candidates=(
            _candidate(
                candidate_id="stat.801",
                statistic_type=StatisticType.CORRELATION,
                value_raw="0.61",
                value_normalized=0.61,
                evidence_span_id="sen.801",
            ),
        ),
    )
    insufficient = rate_hypotheses_testing_for_construct_validity(
        study_id="study.802",
        instrument_id="inst.802",
        prerequisite_decisions=(
            PrerequisiteDecision(
                name=REQUIRED_HYPOTHESES_PREREQUISITE_NAME,
                status=PrerequisiteStatus.MET,
            ),
        ),
        statistic_candidates=(
            _candidate(
                candidate_id="stat.802",
                statistic_type=StatisticType.CORRELATION,
                value_raw="0.22",
                value_normalized=0.22,
                evidence_span_id="sen.802",
            ),
        ),
    )
    missing_hypotheses = rate_hypotheses_testing_for_construct_validity(
        study_id="study.803",
        instrument_id="inst.803",
        statistic_candidates=(
            _candidate(
                candidate_id="stat.803",
                statistic_type=StatisticType.CORRELATION,
                value_raw="0.70",
                value_normalized=0.70,
                evidence_span_id="sen.803",
            ),
        ),
    )

    assert sufficient.computed_rating is MeasurementPropertyRating.SUFFICIENT
    assert insufficient.computed_rating is MeasurementPropertyRating.INSUFFICIENT
    assert missing_hypotheses.computed_rating is MeasurementPropertyRating.INDETERMINATE
    assert missing_hypotheses.uncertainty_status is UncertaintyStatus.MISSING_EVIDENCE


def test_construct_validity_conflicting_and_non_prom_adaptation_paths() -> None:
    conflicting = rate_hypotheses_testing_for_construct_validity(
        study_id="study.804",
        instrument_id="inst.804",
        prerequisite_decisions=(
            PrerequisiteDecision(
                name=REQUIRED_HYPOTHESES_PREREQUISITE_NAME,
                status=PrerequisiteStatus.MET,
            ),
        ),
        statistic_candidates=(
            _candidate(
                candidate_id="stat.804",
                statistic_type=StatisticType.CORRELATION,
                value_raw="0.62",
                value_normalized=0.62,
                evidence_span_id="sen.804",
            ),
            _candidate(
                candidate_id="stat.805",
                statistic_type=StatisticType.AUC,
                value_raw="0.64",
                value_normalized=0.64,
                evidence_span_id="sen.805",
            ),
        ),
    )
    pbom_missing_adaptation = rate_hypotheses_testing_for_construct_validity(
        study_id="study.805",
        instrument_id="inst.805",
        profile_type="pbom",
        prerequisite_decisions=(
            PrerequisiteDecision(
                name=REQUIRED_HYPOTHESES_PREREQUISITE_NAME,
                status=PrerequisiteStatus.MET,
            ),
        ),
        statistic_candidates=(
            _candidate(
                candidate_id="stat.806",
                statistic_type=StatisticType.CORRELATION,
                value_raw="0.70",
                value_normalized=0.70,
                evidence_span_id="sen.806",
            ),
        ),
    )

    assert conflicting.computed_rating is MeasurementPropertyRating.INCONSISTENT
    assert pbom_missing_adaptation.computed_rating is MeasurementPropertyRating.INDETERMINATE
    assert pbom_missing_adaptation.uncertainty_status is UncertaintyStatus.REVIEWER_REQUIRED


def test_responsiveness_paths_and_profile_handling() -> None:
    sufficient = rate_responsiveness(
        study_id="study.901",
        instrument_id="inst.901",
        prerequisite_decisions=(
            PrerequisiteDecision(
                name=REQUIRED_HYPOTHESES_PREREQUISITE_NAME,
                status=PrerequisiteStatus.MET,
            ),
        ),
        statistic_candidates=(
            _candidate(
                candidate_id="stat.901",
                statistic_type=StatisticType.RESPONSIVENESS_RELATED_STATISTIC,
                value_raw="0.80",
                value_normalized=0.80,
                evidence_span_id="sen.901",
            ),
        ),
    )
    insufficient = rate_responsiveness(
        study_id="study.902",
        instrument_id="inst.902",
        prerequisite_decisions=(
            PrerequisiteDecision(
                name=REQUIRED_HYPOTHESES_PREREQUISITE_NAME,
                status=PrerequisiteStatus.MET,
            ),
        ),
        statistic_candidates=(
            _candidate(
                candidate_id="stat.902",
                statistic_type=StatisticType.RESPONSIVENESS_RELATED_STATISTIC,
                value_raw="0.20",
                value_normalized=0.20,
                evidence_span_id="sen.902",
            ),
        ),
    )
    conflicting = rate_responsiveness(
        study_id="study.903",
        instrument_id="inst.903",
        prerequisite_decisions=(
            PrerequisiteDecision(
                name=REQUIRED_HYPOTHESES_PREREQUISITE_NAME,
                status=PrerequisiteStatus.MET,
            ),
        ),
        statistic_candidates=(
            _candidate(
                candidate_id="stat.903",
                statistic_type=StatisticType.RESPONSIVENESS_RELATED_STATISTIC,
                value_raw="0.82",
                value_normalized=0.82,
                evidence_span_id="sen.903",
            ),
            _candidate(
                candidate_id="stat.904",
                statistic_type=StatisticType.AUC,
                value_raw="0.61",
                value_normalized=0.61,
                evidence_span_id="sen.904",
            ),
        ),
    )
    missing_hypotheses = rate_responsiveness(
        study_id="study.904",
        instrument_id="inst.904",
        statistic_candidates=(
            _candidate(
                candidate_id="stat.905",
                statistic_type=StatisticType.RESPONSIVENESS_RELATED_STATISTIC,
                value_raw="0.90",
                value_normalized=0.90,
                evidence_span_id="sen.905",
            ),
        ),
    )

    assert sufficient.computed_rating is MeasurementPropertyRating.SUFFICIENT
    assert insufficient.computed_rating is MeasurementPropertyRating.INSUFFICIENT
    assert conflicting.computed_rating is MeasurementPropertyRating.INCONSISTENT
    assert missing_hypotheses.computed_rating is MeasurementPropertyRating.INDETERMINATE
    assert missing_hypotheses.uncertainty_status is UncertaintyStatus.MISSING_EVIDENCE


def test_responsiveness_non_prom_adaptation_and_activity_supported_path() -> None:
    pbom_missing_adaptation = rate_responsiveness(
        study_id="study.905",
        instrument_id="inst.905",
        profile_type="pbom",
        prerequisite_decisions=(
            PrerequisiteDecision(
                name=REQUIRED_HYPOTHESES_PREREQUISITE_NAME,
                status=PrerequisiteStatus.MET,
            ),
        ),
        statistic_candidates=(
            _candidate(
                candidate_id="stat.906",
                statistic_type=StatisticType.RESPONSIVENESS_RELATED_STATISTIC,
                value_raw="0.75",
                value_normalized=0.75,
                evidence_span_id="sen.906",
            ),
        ),
    )
    activity_sufficient = rate_responsiveness(
        study_id="study.906",
        instrument_id="inst.906",
        profile_type="activity_measure",
        prerequisite_decisions=(
            PrerequisiteDecision(
                name=REQUIRED_HYPOTHESES_PREREQUISITE_NAME,
                status=PrerequisiteStatus.MET,
            ),
            PrerequisiteDecision(
                name=REQUIRED_NON_PROM_ADAPTATION_PREREQUISITE_NAME,
                status=PrerequisiteStatus.MET,
            ),
        ),
        statistic_candidates=(
            _candidate(
                candidate_id="stat.907",
                statistic_type=StatisticType.RESPONSIVENESS_RELATED_STATISTIC,
                value_raw="0.74",
                value_normalized=0.74,
                evidence_span_id="sen.907",
            ),
        ),
    )

    assert pbom_missing_adaptation.computed_rating is MeasurementPropertyRating.INDETERMINATE
    assert pbom_missing_adaptation.uncertainty_status is UncertaintyStatus.REVIEWER_REQUIRED
    assert activity_sufficient.computed_rating is MeasurementPropertyRating.SUFFICIENT
