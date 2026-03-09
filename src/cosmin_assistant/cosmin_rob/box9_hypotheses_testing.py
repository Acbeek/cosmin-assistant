"""COSMIN RoB Box 9 (Hypotheses testing for construct validity)."""

from __future__ import annotations

from cosmin_assistant.cosmin_rob.aggregation import aggregate_box_assessment
from cosmin_assistant.cosmin_rob.item_utils import build_item_assessments_for_box
from cosmin_assistant.cosmin_rob.models import BoxAssessmentBundle, BoxItemInput
from cosmin_assistant.models import StableId

BOX_9_MEASUREMENT_PROPERTY = "hypotheses_testing_for_construct_validity"
BOX_9_KEY = "box_9_hypotheses_testing_for_construct_validity"
BOX_9_ITEM_CODES = (
    "B9.1_hypotheses_predefined",
    "B9.2_comparator_measurement_quality",
    "B9.3_design_and_subgroup_appropriateness",
    "B9.4_statistical_analysis_appropriateness",
    "B9.5_other_important_flaws",
)


def assess_box9_hypotheses_testing_for_construct_validity(
    *,
    study_id: StableId,
    instrument_id: StableId,
    item_inputs: tuple[BoxItemInput, ...],
) -> BoxAssessmentBundle:
    """Assess COSMIN RoB Box 9 using explicit item ratings and evidence links."""

    item_assessments = build_item_assessments_for_box(
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=BOX_9_MEASUREMENT_PROPERTY,
        cosmin_box=BOX_9_KEY,
        item_inputs=item_inputs,
        expected_item_codes=BOX_9_ITEM_CODES,
    )
    return aggregate_box_assessment(
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=BOX_9_MEASUREMENT_PROPERTY,
        cosmin_box=BOX_9_KEY,
        item_assessments=item_assessments,
    )
