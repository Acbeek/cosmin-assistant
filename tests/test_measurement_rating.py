"""Tests for deterministic study-level measurement property rating functions."""

from __future__ import annotations

from cosmin_assistant.extract import StatisticCandidate, StatisticType
from cosmin_assistant.measurement_rating import (
    REQUIRED_PREREQUISITE_NAME,
    PrerequisiteDecision,
    PrerequisiteStatus,
    rate_internal_consistency,
    rate_reliability,
    rate_structural_validity,
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
    value_normalized: float | str | None,
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


def test_structural_validity_sufficient_is_deterministic_and_auditable() -> None:
    result = rate_structural_validity(
        study_id="study.201",
        instrument_id="inst.201",
        statistic_candidates=(
            _candidate(
                candidate_id="stat.201",
                statistic_type=StatisticType.CFI,
                value_raw="0.97",
                value_normalized=0.97,
                evidence_span_id="sen.201",
            ),
            _candidate(
                candidate_id="stat.202",
                statistic_type=StatisticType.RMSEA,
                value_raw="0.05",
                value_normalized=0.05,
                evidence_span_id="sen.202",
            ),
        ),
    )

    assert result.computed_rating is MeasurementPropertyRating.SUFFICIENT
    assert result.rule_name == "MPR_STRUCTURAL_VALIDITY_PROM_V1"
    assert result.explanation
    assert result.inputs_used
    assert result.threshold_comparisons
    assert set(result.evidence_span_ids) == {"sen.201", "sen.202"}


def test_structural_validity_conflicting_results_stay_inconsistent() -> None:
    result = rate_structural_validity(
        study_id="study.203",
        instrument_id="inst.203",
        statistic_candidates=(
            _candidate(
                candidate_id="stat.203",
                statistic_type=StatisticType.CFI,
                value_raw="0.96",
                value_normalized=0.96,
                evidence_span_id="sen.203",
            ),
            _candidate(
                candidate_id="stat.204",
                statistic_type=StatisticType.RMSEA,
                value_raw="0.11",
                value_normalized=0.11,
                evidence_span_id="sen.204",
            ),
        ),
    )

    assert result.computed_rating is MeasurementPropertyRating.INCONSISTENT
    assert result.uncertainty_status is UncertaintyStatus.CONFLICTING
    assert result.reviewer_decision_status is ReviewerDecisionStatus.PENDING


def test_structural_validity_accepts_direct_internal_structure_findings() -> None:
    result = rate_structural_validity(
        study_id="study.205",
        instrument_id="inst.205",
        statistic_candidates=(
            _candidate(
                candidate_id="stat.205",
                statistic_type=StatisticType.INTERNAL_STRUCTURE_FINDING,
                value_raw="rasch internal structure reported",
                value_normalized="reported",
                evidence_span_id="sen.205",
            ),
        ),
    )

    assert result.computed_rating is MeasurementPropertyRating.SUFFICIENT
    assert any(
        comparison.statistic_type is StatisticType.INTERNAL_STRUCTURE_FINDING
        for comparison in result.threshold_comparisons
    )


def test_internal_consistency_returns_indeterminate_when_prerequisite_missing() -> None:
    result = rate_internal_consistency(
        study_id="study.301",
        instrument_id="inst.301",
        statistic_candidates=(
            _candidate(
                candidate_id="stat.301",
                statistic_type=StatisticType.CRONBACH_ALPHA,
                value_raw="0.84",
                value_normalized=0.84,
                evidence_span_id="sen.301",
            ),
        ),
    )

    assert result.computed_rating is MeasurementPropertyRating.INDETERMINATE
    assert result.prerequisite_decisions[0].name == REQUIRED_PREREQUISITE_NAME
    assert result.prerequisite_decisions[0].status is PrerequisiteStatus.MISSING
    assert result.uncertainty_status is UncertaintyStatus.MISSING_EVIDENCE


def test_internal_consistency_sufficient_and_insufficient_paths() -> None:
    prerequisite = (
        PrerequisiteDecision(
            name=REQUIRED_PREREQUISITE_NAME,
            status=PrerequisiteStatus.MET,
            evidence_span_ids=("sen.390",),
        ),
    )
    sufficient = rate_internal_consistency(
        study_id="study.302",
        instrument_id="inst.302",
        statistic_candidates=(
            _candidate(
                candidate_id="stat.302",
                statistic_type=StatisticType.CRONBACH_ALPHA,
                value_raw="0.88",
                value_normalized=0.88,
                evidence_span_id="sen.302",
            ),
        ),
        prerequisite_decisions=prerequisite,
    )
    insufficient = rate_internal_consistency(
        study_id="study.303",
        instrument_id="inst.303",
        statistic_candidates=(
            _candidate(
                candidate_id="stat.303",
                statistic_type=StatisticType.CRONBACH_ALPHA,
                value_raw="0.52",
                value_normalized=0.52,
                evidence_span_id="sen.303",
            ),
        ),
        prerequisite_decisions=prerequisite,
    )

    assert sufficient.computed_rating is MeasurementPropertyRating.SUFFICIENT
    assert insufficient.computed_rating is MeasurementPropertyRating.INSUFFICIENT
    assert sufficient.rule_name == "MPR_INTERNAL_CONSISTENCY_PROM_V1"
    assert insufficient.threshold_comparisons


def test_internal_consistency_conflicting_results_are_not_silently_resolved() -> None:
    result = rate_internal_consistency(
        study_id="study.304",
        instrument_id="inst.304",
        statistic_candidates=(
            _candidate(
                candidate_id="stat.304",
                statistic_type=StatisticType.CRONBACH_ALPHA,
                value_raw="0.90",
                value_normalized=0.90,
                evidence_span_id="sen.304",
            ),
            _candidate(
                candidate_id="stat.305",
                statistic_type=StatisticType.CRONBACH_ALPHA,
                value_raw="0.60",
                value_normalized=0.60,
                evidence_span_id="sen.305",
            ),
        ),
        prerequisite_decisions=(
            PrerequisiteDecision(
                name=REQUIRED_PREREQUISITE_NAME,
                status=PrerequisiteStatus.MET,
                evidence_span_ids=("sen.391",),
            ),
        ),
    )

    assert result.computed_rating is MeasurementPropertyRating.INCONSISTENT
    assert result.uncertainty_status is UncertaintyStatus.CONFLICTING


def test_reliability_sufficient_and_insufficient_paths() -> None:
    sufficient = rate_reliability(
        study_id="study.401",
        instrument_id="inst.401",
        statistic_candidates=(
            _candidate(
                candidate_id="stat.401",
                statistic_type=StatisticType.ICC,
                value_raw="0.82",
                value_normalized=0.82,
                evidence_span_id="sen.401",
            ),
            _candidate(
                candidate_id="stat.402",
                statistic_type=StatisticType.WEIGHTED_KAPPA,
                value_raw="0.76",
                value_normalized=0.76,
                evidence_span_id="sen.402",
            ),
        ),
    )
    insufficient = rate_reliability(
        study_id="study.402",
        instrument_id="inst.402",
        statistic_candidates=(
            _candidate(
                candidate_id="stat.403",
                statistic_type=StatisticType.ICC,
                value_raw="0.60",
                value_normalized=0.60,
                evidence_span_id="sen.403",
            ),
        ),
    )

    assert sufficient.computed_rating is MeasurementPropertyRating.SUFFICIENT
    assert insufficient.computed_rating is MeasurementPropertyRating.INSUFFICIENT
    assert sufficient.rule_name == "MPR_RELIABILITY_PROM_V1"
    assert sufficient.threshold_comparisons


def test_reliability_conflicting_and_missing_data_paths() -> None:
    conflicting = rate_reliability(
        study_id="study.403",
        instrument_id="inst.403",
        statistic_candidates=(
            _candidate(
                candidate_id="stat.404",
                statistic_type=StatisticType.ICC,
                value_raw="0.80",
                value_normalized=0.80,
                evidence_span_id="sen.404",
            ),
            _candidate(
                candidate_id="stat.405",
                statistic_type=StatisticType.ICC,
                value_raw="0.62",
                value_normalized=0.62,
                evidence_span_id="sen.405",
            ),
        ),
    )
    missing = rate_reliability(
        study_id="study.404",
        instrument_id="inst.404",
        statistic_candidates=(),
    )

    assert conflicting.computed_rating is MeasurementPropertyRating.INCONSISTENT
    assert conflicting.uncertainty_status is UncertaintyStatus.CONFLICTING
    assert missing.computed_rating is MeasurementPropertyRating.INDETERMINATE
    assert missing.uncertainty_status is UncertaintyStatus.MISSING_EVIDENCE
