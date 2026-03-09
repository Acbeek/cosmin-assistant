"""Tests for COSMIN RoB item utilities and box aggregation behavior."""

from __future__ import annotations

from cosmin_assistant.cosmin_rob import (
    BoxItemInput,
    aggregate_box_assessment,
    build_item_assessment,
)
from cosmin_assistant.models import (
    CosminBoxRating,
    CosminItemRating,
    ReviewerDecisionStatus,
    UncertaintyStatus,
)


def _item(
    *,
    item_code: str,
    item_rating: CosminItemRating,
    evidence_span_ids: list[str],
) -> BoxItemInput:
    return BoxItemInput(
        item_code=item_code,
        item_rating=item_rating,
        evidence_span_ids=evidence_span_ids,
    )


def test_item_assessment_structure_is_evidence_linked() -> None:
    item_assessment = build_item_assessment(
        study_id="study.1",
        instrument_id="inst.1",
        measurement_property="reliability",
        cosmin_box="box_6_reliability",
        item_input=_item(
            item_code="B6.1_stability_of_patients",
            item_rating=CosminItemRating.ADEQUATE,
            evidence_span_ids=["sen.10", "sen.11"],
        ),
    )

    assert item_assessment.item_code == "B6.1_stability_of_patients"
    assert item_assessment.item_rating is CosminItemRating.ADEQUATE
    assert item_assessment.evidence_span_ids == ["sen.10", "sen.11"]
    assert item_assessment.uncertainty_status is UncertaintyStatus.CERTAIN
    assert item_assessment.reviewer_decision_status is ReviewerDecisionStatus.NOT_REQUIRED


def test_box_aggregation_applies_worst_score_counts() -> None:
    item_assessments = (
        build_item_assessment(
            study_id="study.1",
            instrument_id="inst.1",
            measurement_property="structural_validity",
            cosmin_box="box_3_structural_validity",
            item_input=_item(
                item_code="B3.1_ctt_factor_analysis_performed",
                item_rating=CosminItemRating.VERY_GOOD,
                evidence_span_ids=["sen.1"],
            ),
        ),
        build_item_assessment(
            study_id="study.1",
            instrument_id="inst.1",
            measurement_property="structural_validity",
            cosmin_box="box_3_structural_validity",
            item_input=_item(
                item_code="B3.2_irt_or_rasch_model_fit",
                item_rating=CosminItemRating.INADEQUATE,
                evidence_span_ids=["sen.2"],
            ),
        ),
    )

    bundle = aggregate_box_assessment(
        study_id="study.1",
        instrument_id="inst.1",
        measurement_property="structural_validity",
        cosmin_box="box_3_structural_validity",
        item_assessments=item_assessments,
    )

    assert bundle.box_assessment.box_rating is CosminBoxRating.INADEQUATE
    assert bundle.worst_score_counts_applied is True
    assert bundle.worst_item_assessment_ids == (item_assessments[1].id,)


def test_na_items_are_excluded_from_worst_score_counts() -> None:
    item_assessments = (
        build_item_assessment(
            study_id="study.2",
            instrument_id="inst.2",
            measurement_property="internal_consistency",
            cosmin_box="box_4_internal_consistency",
            item_input=_item(
                item_code="B4.1_continuous_scores_alpha_or_omega",
                item_rating=CosminItemRating.ADEQUATE,
                evidence_span_ids=["sen.20"],
            ),
        ),
        build_item_assessment(
            study_id="study.2",
            instrument_id="inst.2",
            measurement_property="internal_consistency",
            cosmin_box="box_4_internal_consistency",
            item_input=_item(
                item_code="B4.2_dichotomous_scores_alpha_or_kr20",
                item_rating=CosminItemRating.NOT_APPLICABLE,
                evidence_span_ids=["sen.21"],
            ),
        ),
        build_item_assessment(
            study_id="study.2",
            instrument_id="inst.2",
            measurement_property="internal_consistency",
            cosmin_box="box_4_internal_consistency",
            item_input=_item(
                item_code="B4.3_irt_scores_se_theta_or_reliability",
                item_rating=CosminItemRating.DOUBTFUL,
                evidence_span_ids=["sen.22"],
            ),
        ),
    )

    bundle = aggregate_box_assessment(
        study_id="study.2",
        instrument_id="inst.2",
        measurement_property="internal_consistency",
        cosmin_box="box_4_internal_consistency",
        item_assessments=item_assessments,
    )

    assert bundle.box_assessment.box_rating is CosminBoxRating.DOUBTFUL
    assert bundle.not_applicable_item_assessment_ids == (item_assessments[1].id,)
    assert item_assessments[1].id not in bundle.worst_item_assessment_ids


def test_all_na_items_produce_indeterminate_box_with_explicit_na_metadata() -> None:
    item_assessments = (
        build_item_assessment(
            study_id="study.3",
            instrument_id="inst.3",
            measurement_property="internal_consistency",
            cosmin_box="box_4_internal_consistency",
            item_input=_item(
                item_code="B4.1_continuous_scores_alpha_or_omega",
                item_rating=CosminItemRating.NOT_APPLICABLE,
                evidence_span_ids=["sen.30"],
            ),
        ),
        build_item_assessment(
            study_id="study.3",
            instrument_id="inst.3",
            measurement_property="internal_consistency",
            cosmin_box="box_4_internal_consistency",
            item_input=_item(
                item_code="B4.2_dichotomous_scores_alpha_or_kr20",
                item_rating=CosminItemRating.NOT_APPLICABLE,
                evidence_span_ids=["sen.31"],
            ),
        ),
    )

    bundle = aggregate_box_assessment(
        study_id="study.3",
        instrument_id="inst.3",
        measurement_property="internal_consistency",
        cosmin_box="box_4_internal_consistency",
        item_assessments=item_assessments,
    )

    assert bundle.box_assessment.box_rating is CosminBoxRating.INDETERMINATE
    assert bundle.applicable_item_assessment_ids == ()
    assert bundle.not_applicable_item_assessment_ids == (
        item_assessments[0].id,
        item_assessments[1].id,
    )
    assert bundle.box_assessment.uncertainty_status is UncertaintyStatus.MISSING_EVIDENCE
    assert bundle.box_assessment.reviewer_decision_status is ReviewerDecisionStatus.PENDING
