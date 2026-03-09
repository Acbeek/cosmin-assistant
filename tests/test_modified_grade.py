"""Tests for modified GRADE downgrading and certainty transitions."""

from __future__ import annotations

import pytest

from cosmin_assistant.grade import (
    DomainDowngradeInput,
    DowngradeSeverity,
    ModifiedGradeDomain,
    apply_modified_grade,
)
from cosmin_assistant.models import EvidenceCertaintyLevel, MeasurementPropertyRating
from cosmin_assistant.synthesize import StudySynthesisInput, synthesize_first_pass


def _study_result(
    *,
    result_id: str,
    study_id: str,
    rating: MeasurementPropertyRating,
    sample_size: int,
    evidence_span_id: str,
) -> StudySynthesisInput:
    return StudySynthesisInput(
        id=result_id,
        study_id=study_id,
        instrument_name="PROM-G",
        instrument_version="v1",
        subscale="total",
        measurement_property="reliability",
        rating=rating,
        sample_size=sample_size,
        evidence_span_ids=(evidence_span_id,),
    )


def test_modified_grade_starts_high_and_downgrades_explicitly() -> None:
    synthesis = synthesize_first_pass(
        (
            _study_result(
                result_id="mpr.1",
                study_id="study.1",
                rating=MeasurementPropertyRating.SUFFICIENT,
                sample_size=160,
                evidence_span_id="sen.1",
            ),
        )
    )[0]

    grade = apply_modified_grade(
        synthesis_result=synthesis,
        risk_of_bias=DomainDowngradeInput(
            domain=ModifiedGradeDomain.RISK_OF_BIAS,
            severity=DowngradeSeverity.SERIOUS,
            reason="Most studies had doubtful methodological quality.",
            evidence_span_ids=("sen.1",),
            explanation="Risk of bias downgraded by one level.",
        ),
        indirectness=DomainDowngradeInput(
            domain=ModifiedGradeDomain.INDIRECTNESS,
            severity=DowngradeSeverity.NONE,
            reason=None,
            evidence_span_ids=(),
            explanation=None,
        ),
    )

    assert grade.starting_certainty is EvidenceCertaintyLevel.HIGH
    assert grade.final_certainty is EvidenceCertaintyLevel.MODERATE
    assert len(grade.domain_decisions) == 4
    assert len(grade.downgrade_records) == 1
    record = grade.downgrade_records[0]
    assert record.domain is ModifiedGradeDomain.RISK_OF_BIAS
    assert record.reason
    assert record.explanation
    assert record.evidence_span_ids == ("sen.1",)


def test_sample_size_drives_imprecision_downgrading() -> None:
    synthesis_serious = synthesize_first_pass(
        (
            _study_result(
                result_id="mpr.2",
                study_id="study.2",
                rating=MeasurementPropertyRating.SUFFICIENT,
                sample_size=75,
                evidence_span_id="sen.2",
            ),
        )
    )[0]
    synthesis_very_serious = synthesize_first_pass(
        (
            _study_result(
                result_id="mpr.3",
                study_id="study.3",
                rating=MeasurementPropertyRating.SUFFICIENT,
                sample_size=40,
                evidence_span_id="sen.3",
            ),
        )
    )[0]

    common_none = DomainDowngradeInput(
        domain=ModifiedGradeDomain.RISK_OF_BIAS,
        severity=DowngradeSeverity.NONE,
        reason=None,
        evidence_span_ids=(),
        explanation=None,
    )
    indirect_none = DomainDowngradeInput(
        domain=ModifiedGradeDomain.INDIRECTNESS,
        severity=DowngradeSeverity.NONE,
        reason=None,
        evidence_span_ids=(),
        explanation=None,
    )

    grade_serious = apply_modified_grade(
        synthesis_result=synthesis_serious,
        risk_of_bias=common_none,
        indirectness=indirect_none,
    )
    grade_very_serious = apply_modified_grade(
        synthesis_result=synthesis_very_serious,
        risk_of_bias=common_none,
        indirectness=indirect_none,
    )

    assert grade_serious.final_certainty is EvidenceCertaintyLevel.MODERATE
    assert any(
        record.domain is ModifiedGradeDomain.IMPRECISION
        and record.severity is DowngradeSeverity.SERIOUS
        for record in grade_serious.downgrade_records
    )
    assert grade_very_serious.final_certainty is EvidenceCertaintyLevel.LOW
    assert any(
        record.domain is ModifiedGradeDomain.IMPRECISION
        and record.severity is DowngradeSeverity.VERY_SERIOUS
        and record.downgrade_steps == 2
        for record in grade_very_serious.downgrade_records
    )


def test_inconsistency_domain_auto_downgrades_when_synthesis_is_inconsistent() -> None:
    synthesis = synthesize_first_pass(
        (
            _study_result(
                result_id="mpr.10",
                study_id="study.10",
                rating=MeasurementPropertyRating.SUFFICIENT,
                sample_size=120,
                evidence_span_id="sen.10",
            ),
            _study_result(
                result_id="mpr.11",
                study_id="study.11",
                rating=MeasurementPropertyRating.INSUFFICIENT,
                sample_size=130,
                evidence_span_id="sen.11",
            ),
        )
    )[0]

    grade = apply_modified_grade(
        synthesis_result=synthesis,
        risk_of_bias=DomainDowngradeInput(
            domain=ModifiedGradeDomain.RISK_OF_BIAS,
            severity=DowngradeSeverity.NONE,
            reason=None,
            evidence_span_ids=(),
            explanation=None,
        ),
        indirectness=DomainDowngradeInput(
            domain=ModifiedGradeDomain.INDIRECTNESS,
            severity=DowngradeSeverity.NONE,
            reason=None,
            evidence_span_ids=(),
            explanation=None,
        ),
    )

    assert synthesis.inconsistent_findings is True
    assert any(
        record.domain is ModifiedGradeDomain.INCONSISTENCY
        and record.severity is DowngradeSeverity.SERIOUS
        for record in grade.downgrade_records
    )


def test_domain_severity_validation_matches_modified_grade_sheet_domains() -> None:
    synthesis = synthesize_first_pass(
        (
            _study_result(
                result_id="mpr.20",
                study_id="study.20",
                rating=MeasurementPropertyRating.SUFFICIENT,
                sample_size=180,
                evidence_span_id="sen.20",
            ),
        )
    )[0]

    with pytest.raises(ValueError, match="severity extremely_serious is not allowed"):
        apply_modified_grade(
            synthesis_result=synthesis,
            risk_of_bias=DomainDowngradeInput(
                domain=ModifiedGradeDomain.RISK_OF_BIAS,
                severity=DowngradeSeverity.NONE,
                reason=None,
                evidence_span_ids=(),
                explanation=None,
            ),
            indirectness=DomainDowngradeInput(
                domain=ModifiedGradeDomain.INDIRECTNESS,
                severity=DowngradeSeverity.EXTREMELY_SERIOUS,
                reason="Construct mismatch was extreme.",
                evidence_span_ids=("sen.20",),
                explanation="Indirectness marked as extremely serious.",
            ),
        )
