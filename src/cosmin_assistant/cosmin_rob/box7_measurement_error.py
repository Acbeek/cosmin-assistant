"""COSMIN RoB Box 7 (Measurement error)."""

from __future__ import annotations

from cosmin_assistant.cosmin_rob.aggregation import aggregate_box_assessment
from cosmin_assistant.cosmin_rob.item_utils import build_item_assessments_for_box
from cosmin_assistant.cosmin_rob.models import BoxAssessmentBundle, BoxItemInput
from cosmin_assistant.models import StableId

BOX_7_MEASUREMENT_PROPERTY = "measurement_error"
BOX_7_KEY = "box_7_measurement_error"
BOX_7_ITEM_CODES = (
    "B7.1_stability_between_measurements",
    "B7.2_time_interval_appropriateness",
    "B7.3_measurement_conditions_similarity",
    "B7.4_appropriate_error_parameter",
    "B7.5_comparison_with_mic_or_relevant_threshold",
    "B7.6_other_important_flaws",
)


def assess_box7_measurement_error(
    *,
    study_id: StableId,
    instrument_id: StableId,
    item_inputs: tuple[BoxItemInput, ...],
) -> BoxAssessmentBundle:
    """Assess COSMIN RoB Box 7 using explicit item ratings and evidence links."""

    item_assessments = build_item_assessments_for_box(
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=BOX_7_MEASUREMENT_PROPERTY,
        cosmin_box=BOX_7_KEY,
        item_inputs=item_inputs,
        expected_item_codes=BOX_7_ITEM_CODES,
    )
    return aggregate_box_assessment(
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=BOX_7_MEASUREMENT_PROPERTY,
        cosmin_box=BOX_7_KEY,
        item_assessments=item_assessments,
    )
