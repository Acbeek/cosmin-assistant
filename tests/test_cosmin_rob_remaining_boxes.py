"""Tests for remaining modular COSMIN RoB boxes (1, 2, 5, 7, 8, 9, 10)."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from cosmin_assistant.cosmin_rob import (
    BOX_1_ITEM_CODES,
    BOX_2_ITEM_CODES,
    BOX_5_ITEM_CODES,
    BOX_7_ITEM_CODES,
    BOX_8_ITEM_CODES,
    BOX_9_ITEM_CODES,
    BOX_10_ITEM_CODES,
    BoxAssessmentBundle,
    BoxItemInput,
    assess_box1_prom_development,
    assess_box2_content_validity,
    assess_box5_cross_cultural_validity_measurement_invariance,
    assess_box7_measurement_error,
    assess_box8_criterion_validity,
    assess_box9_hypotheses_testing_for_construct_validity,
    assess_box10_responsiveness,
)
from cosmin_assistant.models import (
    CosminBoxRating,
    CosminItemRating,
    ReviewerDecisionStatus,
    UncertaintyStatus,
)

BoxAssessor = Callable[..., BoxAssessmentBundle]

_BOX_SPECS: tuple[tuple[str, tuple[str, ...], BoxAssessor], ...] = (
    ("box1", BOX_1_ITEM_CODES, assess_box1_prom_development),
    ("box2", BOX_2_ITEM_CODES, assess_box2_content_validity),
    (
        "box5",
        BOX_5_ITEM_CODES,
        assess_box5_cross_cultural_validity_measurement_invariance,
    ),
    ("box7", BOX_7_ITEM_CODES, assess_box7_measurement_error),
    ("box8", BOX_8_ITEM_CODES, assess_box8_criterion_validity),
    (
        "box9",
        BOX_9_ITEM_CODES,
        assess_box9_hypotheses_testing_for_construct_validity,
    ),
    ("box10", BOX_10_ITEM_CODES, assess_box10_responsiveness),
)


def _make_inputs(
    item_codes: tuple[str, ...],
    *,
    default_rating: CosminItemRating,
) -> list[BoxItemInput]:
    return [
        BoxItemInput(
            item_code=item_code,
            item_rating=default_rating,
            evidence_span_ids=[f"sen.{index + 1}"],
        )
        for index, item_code in enumerate(item_codes)
    ]


@pytest.mark.parametrize("box_name,item_codes,assessor", _BOX_SPECS)
def test_remaining_boxes_positive_path_returns_very_good(
    box_name: str,
    item_codes: tuple[str, ...],
    assessor: BoxAssessor,
) -> None:
    bundle = assessor(
        study_id=f"study.{box_name}.positive",
        instrument_id=f"inst.{box_name}.positive",
        item_inputs=tuple(_make_inputs(item_codes, default_rating=CosminItemRating.VERY_GOOD)),
    )

    assert bundle.item_assessments
    assert bundle.box_assessment.evidence_span_ids
    assert bundle.box_assessment.box_rating is CosminBoxRating.VERY_GOOD
    assert bundle.worst_score_counts_applied is True


@pytest.mark.parametrize("box_name,item_codes,assessor", _BOX_SPECS)
def test_remaining_boxes_preserve_reviewer_required_uncertainty_without_forcing_negative_rating(
    box_name: str,
    item_codes: tuple[str, ...],
    assessor: BoxAssessor,
) -> None:
    item_inputs = _make_inputs(item_codes, default_rating=CosminItemRating.ADEQUATE)
    item_inputs[0] = BoxItemInput(
        item_code=item_codes[0],
        item_rating=CosminItemRating.ADEQUATE,
        evidence_span_ids=[f"sen.{box_name}.reviewer"],
        uncertainty_status=UncertaintyStatus.REVIEWER_REQUIRED,
        reviewer_decision_status=ReviewerDecisionStatus.PENDING,
    )

    bundle = assessor(
        study_id=f"study.{box_name}.reviewer",
        instrument_id=f"inst.{box_name}.reviewer",
        item_inputs=tuple(item_inputs),
    )

    assert bundle.box_assessment.box_rating is CosminBoxRating.ADEQUATE
    assert bundle.box_assessment.uncertainty_status is UncertaintyStatus.REVIEWER_REQUIRED
    assert bundle.box_assessment.reviewer_decision_status is ReviewerDecisionStatus.PENDING


@pytest.mark.parametrize("box_name,item_codes,assessor", _BOX_SPECS)
def test_remaining_boxes_na_handling_is_explicit_and_all_na_is_indeterminate(
    box_name: str,
    item_codes: tuple[str, ...],
    assessor: BoxAssessor,
) -> None:
    item_inputs = tuple(
        BoxItemInput(
            item_code=item_code,
            item_rating=CosminItemRating.NOT_APPLICABLE,
            evidence_span_ids=[f"sen.{box_name}.na.{index}"],
        )
        for index, item_code in enumerate(item_codes, start=1)
    )

    bundle = assessor(
        study_id=f"study.{box_name}.na",
        instrument_id=f"inst.{box_name}.na",
        item_inputs=item_inputs,
    )

    assert bundle.box_assessment.box_rating is CosminBoxRating.INDETERMINATE
    assert bundle.applicable_item_assessment_ids == ()
    assert len(bundle.not_applicable_item_assessment_ids) == len(item_codes)
    assert bundle.box_assessment.uncertainty_status is UncertaintyStatus.MISSING_EVIDENCE
    assert bundle.box_assessment.reviewer_decision_status is ReviewerDecisionStatus.PENDING


@pytest.mark.parametrize("box_name,item_codes,assessor", _BOX_SPECS)
def test_remaining_boxes_worst_score_counts_aggregation_behavior(
    box_name: str,
    item_codes: tuple[str, ...],
    assessor: BoxAssessor,
) -> None:
    item_inputs = _make_inputs(item_codes, default_rating=CosminItemRating.VERY_GOOD)
    item_inputs[1] = BoxItemInput(
        item_code=item_codes[1],
        item_rating=CosminItemRating.INADEQUATE,
        evidence_span_ids=[f"sen.{box_name}.worst"],
    )

    bundle = assessor(
        study_id=f"study.{box_name}.worst",
        instrument_id=f"inst.{box_name}.worst",
        item_inputs=tuple(item_inputs),
    )

    assert bundle.box_assessment.box_rating is CosminBoxRating.INADEQUATE
    assert len(bundle.worst_item_assessment_ids) == 1
    assert bundle.worst_item_assessment_ids[0] in {
        item_assessment.id for item_assessment in bundle.item_assessments
    }
