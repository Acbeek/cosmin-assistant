"""COSMIN RoB Box 8 (Criterion validity)."""

from __future__ import annotations

from cosmin_assistant.cosmin_rob.aggregation import aggregate_box_assessment
from cosmin_assistant.cosmin_rob.item_utils import build_item_assessments_for_box
from cosmin_assistant.cosmin_rob.models import BoxAssessmentBundle, BoxItemInput
from cosmin_assistant.models import StableId

BOX_8_MEASUREMENT_PROPERTY = "criterion_validity"
BOX_8_KEY = "box_8_criterion_validity"
BOX_8_ITEM_CODES = (
    "B8.1_gold_standard_quality",
    "B8.2_design_and_methodological_alignment",
    "B8.3_time_interval_and_conditions",
    "B8.4_appropriate_statistical_analysis",
    "B8.5_other_important_flaws",
)


def assess_box8_criterion_validity(
    *,
    study_id: StableId,
    instrument_id: StableId,
    item_inputs: tuple[BoxItemInput, ...],
) -> BoxAssessmentBundle:
    """Assess COSMIN RoB Box 8 using explicit item ratings and evidence links."""

    item_assessments = build_item_assessments_for_box(
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=BOX_8_MEASUREMENT_PROPERTY,
        cosmin_box=BOX_8_KEY,
        item_inputs=item_inputs,
        expected_item_codes=BOX_8_ITEM_CODES,
    )
    return aggregate_box_assessment(
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=BOX_8_MEASUREMENT_PROPERTY,
        cosmin_box=BOX_8_KEY,
        item_assessments=item_assessments,
    )
