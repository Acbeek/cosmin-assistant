"""Validation and JSON round-trip tests for core model layer."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from cosmin_assistant.models import (
    ArticleDocument,
    CosminBoxAssessment,
    CosminBoxRating,
    CosminItemAssessment,
    CosminItemRating,
    EvidenceCertaintyLevel,
    EvidenceSpan,
    ExtractedInstrumentContext,
    ExtractedStatistic,
    ExtractedStudyContext,
    GradeDowngradeDecision,
    HeadingSpan,
    MeasurementPropertyRating,
    MeasurementPropertyStudyResult,
    ModelBase,
    ProfileType,
    ReviewerDecisionStatus,
    ReviewerOverride,
    SummaryOfFindingsRow,
    SynthesisResult,
    UncertaintyStatus,
)


def _derived_payloads() -> list[tuple[type[ModelBase], dict[str, object]]]:
    return [
        (
            ExtractedStatistic,
            {
                "id": "stat.1",
                "article_id": "article.1",
                "study_id": "study.1",
                "instrument_id": "inst.1",
                "statistic_name": "icc",
                "statistic_value": "0.82",
                "evidence_span_ids": ["ev.1"],
                "uncertainty_status": UncertaintyStatus.CERTAIN,
            },
        ),
        (
            ExtractedStudyContext,
            {
                "id": "studyctx.1",
                "article_id": "article.1",
                "study_id": "study.1",
                "study_design": "prospective cohort",
                "evidence_span_ids": ["ev.1"],
                "uncertainty_status": UncertaintyStatus.CERTAIN,
            },
        ),
        (
            ExtractedInstrumentContext,
            {
                "id": "instctx.1",
                "article_id": "article.1",
                "study_id": "study.1",
                "instrument_id": "inst.1",
                "instrument_name": "PROM-X",
                "profile_type": ProfileType.PROM,
                "evidence_span_ids": ["ev.1"],
                "uncertainty_status": UncertaintyStatus.CERTAIN,
            },
        ),
        (
            CosminItemAssessment,
            {
                "id": "item.1",
                "study_id": "study.1",
                "instrument_id": "inst.1",
                "measurement_property": "reliability",
                "cosmin_box": "reliability",
                "item_code": "REL-1",
                "item_rating": CosminItemRating.ADEQUATE,
                "evidence_span_ids": ["ev.1"],
                "uncertainty_status": UncertaintyStatus.CERTAIN,
                "reviewer_decision_status": ReviewerDecisionStatus.NOT_REQUIRED,
            },
        ),
        (
            CosminBoxAssessment,
            {
                "id": "box.1",
                "study_id": "study.1",
                "instrument_id": "inst.1",
                "measurement_property": "reliability",
                "cosmin_box": "reliability",
                "box_rating": CosminBoxRating.ADEQUATE,
                "item_assessment_ids": ["item.1"],
                "evidence_span_ids": ["ev.1"],
                "uncertainty_status": UncertaintyStatus.CERTAIN,
                "reviewer_decision_status": ReviewerDecisionStatus.NOT_REQUIRED,
            },
        ),
        (
            MeasurementPropertyStudyResult,
            {
                "id": "mpr.1",
                "study_id": "study.1",
                "instrument_id": "inst.1",
                "measurement_property": "reliability",
                "rating": MeasurementPropertyRating.SUFFICIENT,
                "box_assessment_ids": ["box.1"],
                "evidence_span_ids": ["ev.1"],
                "uncertainty_status": UncertaintyStatus.CERTAIN,
                "reviewer_decision_status": ReviewerDecisionStatus.NOT_REQUIRED,
            },
        ),
        (
            SynthesisResult,
            {
                "id": "syn.1",
                "instrument_id": "inst.1",
                "measurement_property": "reliability",
                "study_result_ids": ["mpr.1"],
                "rating": MeasurementPropertyRating.SUFFICIENT,
                "evidence_span_ids": ["ev.1"],
                "uncertainty_status": UncertaintyStatus.CERTAIN,
                "reviewer_decision_status": ReviewerDecisionStatus.NOT_REQUIRED,
            },
        ),
        (
            GradeDowngradeDecision,
            {
                "id": "grade.1",
                "synthesis_result_id": "syn.1",
                "downgrade_domain": "imprecision",
                "downgrade_steps": 1,
                "certainty_before": EvidenceCertaintyLevel.HIGH,
                "certainty_after": EvidenceCertaintyLevel.MODERATE,
                "evidence_span_ids": ["ev.1"],
                "uncertainty_status": UncertaintyStatus.CERTAIN,
                "reviewer_decision_status": ReviewerDecisionStatus.NOT_REQUIRED,
            },
        ),
        (
            SummaryOfFindingsRow,
            {
                "id": "sof.1",
                "instrument_id": "inst.1",
                "measurement_property": "reliability",
                "synthesis_result_id": "syn.1",
                "final_rating": MeasurementPropertyRating.SUFFICIENT,
                "evidence_certainty": EvidenceCertaintyLevel.MODERATE,
                "downgrade_decision_ids": ["grade.1"],
                "evidence_span_ids": ["ev.1"],
                "uncertainty_status": UncertaintyStatus.CERTAIN,
                "reviewer_decision_status": ReviewerDecisionStatus.NOT_REQUIRED,
            },
        ),
        (
            ReviewerOverride,
            {
                "id": "override.1",
                "target_object_type": "MeasurementPropertyStudyResult",
                "target_object_id": "mpr.1",
                "reviewer_id": "rev.1",
                "decision_status": ReviewerDecisionStatus.OVERRIDDEN,
                "reason": "Manuscript erratum clarified test interval.",
                "previous_value": "?",
                "overridden_value": "+",
                "evidence_span_ids": ["ev.1"],
                "uncertainty_status": UncertaintyStatus.REVIEWER_REQUIRED,
                "created_at_utc": datetime(2026, 3, 9, tzinfo=UTC),
            },
        ),
    ]


@pytest.mark.parametrize("model_cls,payload", _derived_payloads())
def test_derived_models_require_evidence_span_ids(
    model_cls: type[ModelBase],
    payload: dict[str, object],
) -> None:
    invalid_payload = dict(payload)
    invalid_payload["evidence_span_ids"] = []

    with pytest.raises(ValidationError):
        model_cls(**invalid_payload)


@pytest.mark.parametrize("model_cls,payload", _derived_payloads())
def test_derived_models_round_trip_json(
    model_cls: type[ModelBase],
    payload: dict[str, object],
) -> None:
    instance = model_cls(**payload)
    restored = model_cls.model_validate_json(instance.model_dump_json())

    assert restored == instance
    assert restored.id == payload["id"]


def test_article_heading_and_evidence_span_validate_and_round_trip() -> None:
    article = ArticleDocument(
        id="article.1",
        source_path="data/articles/a1.md",
        markdown_text="# Heading\nBody",
    )
    heading = HeadingSpan(
        id="heading.1",
        article_id="article.1",
        heading_level=1,
        heading_text="Heading",
        start_char=0,
        end_char=8,
    )
    evidence = EvidenceSpan(
        id="ev.1",
        article_id="article.1",
        heading_span_id="heading.1",
        start_char=9,
        end_char=13,
        quoted_text="Body",
    )

    assert ArticleDocument.model_validate_json(article.model_dump_json()) == article
    assert HeadingSpan.model_validate_json(heading.model_dump_json()) == heading
    assert EvidenceSpan.model_validate_json(evidence.model_dump_json()) == evidence


def test_ids_must_use_stable_id_format() -> None:
    with pytest.raises(ValidationError):
        ArticleDocument(
            id="Bad ID With Spaces",
            source_path="data/articles/a1.md",
            markdown_text="# Heading",
        )


def test_uncertainty_and_reviewer_status_must_be_explicit() -> None:
    with pytest.raises(ValidationError):
        CosminItemAssessment(
            id="item.2",
            study_id="study.2",
            instrument_id="inst.2",
            measurement_property="reliability",
            cosmin_box="reliability",
            item_code="REL-2",
            item_rating=CosminItemRating.ADEQUATE,
            evidence_span_ids=["ev.2"],
        )

    with pytest.raises(ValidationError):
        ReviewerOverride(
            id="override.2",
            target_object_type="SynthesisResult",
            target_object_id="syn.2",
            reviewer_id="rev.1",
            reason="Clarified construct mismatch.",
            evidence_span_ids=["ev.2"],
            uncertainty_status=UncertaintyStatus.REVIEWER_REQUIRED,
        )
