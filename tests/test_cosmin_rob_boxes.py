"""Tests for initial modular COSMIN RoB box assessors (Box 3, 4, and 6)."""

from __future__ import annotations

import pytest

from cosmin_assistant.cosmin_rob import (
    BOX_3_ITEM_CODES,
    BOX_4_ITEM_CODES,
    BOX_6_ITEM_CODES,
    BoxItemInput,
    assess_box3_structural_validity,
    assess_box4_internal_consistency,
    assess_box6_reliability,
)
from cosmin_assistant.models import CosminBoxRating, CosminItemRating


def _make_inputs(
    item_codes: tuple[str, ...],
    default_rating: CosminItemRating = CosminItemRating.VERY_GOOD,
) -> tuple[BoxItemInput, ...]:
    return tuple(
        BoxItemInput(
            item_code=item_code,
            item_rating=default_rating,
            evidence_span_ids=[f"sen.{index + 1}"],
        )
        for index, item_code in enumerate(item_codes)
    )


def test_box_modules_return_structured_evidence_linked_outputs() -> None:
    box3 = assess_box3_structural_validity(
        study_id="study.10",
        instrument_id="inst.10",
        item_inputs=_make_inputs(BOX_3_ITEM_CODES),
    )
    box4 = assess_box4_internal_consistency(
        study_id="study.10",
        instrument_id="inst.10",
        item_inputs=_make_inputs(BOX_4_ITEM_CODES),
    )
    box6 = assess_box6_reliability(
        study_id="study.10",
        instrument_id="inst.10",
        item_inputs=_make_inputs(BOX_6_ITEM_CODES),
    )

    for bundle in (box3, box4, box6):
        assert bundle.item_assessments
        assert bundle.box_assessment.evidence_span_ids
        assert bundle.aggregation_rule == "ROB_WORST_SCORE_COUNTS_V1"
        assert bundle.na_handling_rule == "ROB_NA_EXCLUSION_V1"


def test_box_modules_require_explicit_item_coverage() -> None:
    with pytest.raises(ValueError, match="item coverage mismatch"):
        assess_box3_structural_validity(
            study_id="study.11",
            instrument_id="inst.11",
            item_inputs=_make_inputs(BOX_3_ITEM_CODES[:-1]),
        )

    duplicated = _make_inputs(BOX_4_ITEM_CODES[:-1]) + (
        BoxItemInput(
            item_code=BOX_4_ITEM_CODES[0],
            item_rating=CosminItemRating.ADEQUATE,
            evidence_span_ids=["sen.999"],
        ),
    )
    with pytest.raises(ValueError, match="duplicate item_code"):
        assess_box4_internal_consistency(
            study_id="study.11",
            instrument_id="inst.11",
            item_inputs=duplicated,
        )


def test_single_inadequate_item_forces_inadequate_box_rating() -> None:
    item_inputs = list(_make_inputs(BOX_6_ITEM_CODES, default_rating=CosminItemRating.VERY_GOOD))
    item_inputs[4] = BoxItemInput(
        item_code=BOX_6_ITEM_CODES[4],
        item_rating=CosminItemRating.INADEQUATE,
        evidence_span_ids=["sen.500"],
    )

    bundle = assess_box6_reliability(
        study_id="study.12",
        instrument_id="inst.12",
        item_inputs=tuple(item_inputs),
    )

    assert bundle.box_assessment.box_rating is CosminBoxRating.INADEQUATE
    assert len(bundle.worst_item_assessment_ids) == 1


def test_box4_na_handling_is_explicit_and_excluded_from_worst_score() -> None:
    item_inputs = (
        BoxItemInput(
            item_code=BOX_4_ITEM_CODES[0],
            item_rating=CosminItemRating.ADEQUATE,
            evidence_span_ids=["sen.601"],
        ),
        BoxItemInput(
            item_code=BOX_4_ITEM_CODES[1],
            item_rating=CosminItemRating.NOT_APPLICABLE,
            evidence_span_ids=["sen.602"],
        ),
        BoxItemInput(
            item_code=BOX_4_ITEM_CODES[2],
            item_rating=CosminItemRating.NOT_APPLICABLE,
            evidence_span_ids=["sen.603"],
        ),
        BoxItemInput(
            item_code=BOX_4_ITEM_CODES[3],
            item_rating=CosminItemRating.VERY_GOOD,
            evidence_span_ids=["sen.604"],
        ),
    )

    bundle = assess_box4_internal_consistency(
        study_id="study.13",
        instrument_id="inst.13",
        item_inputs=item_inputs,
    )

    assert bundle.box_assessment.box_rating is CosminBoxRating.ADEQUATE
    assert len(bundle.not_applicable_item_assessment_ids) == 2
    assert len(bundle.applicable_item_assessment_ids) == 2
