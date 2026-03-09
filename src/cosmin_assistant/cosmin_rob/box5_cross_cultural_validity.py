"""COSMIN RoB Box 5 (Cross-cultural validity / measurement invariance)."""

from __future__ import annotations

from cosmin_assistant.cosmin_rob.aggregation import aggregate_box_assessment
from cosmin_assistant.cosmin_rob.item_utils import build_item_assessments_for_box
from cosmin_assistant.cosmin_rob.models import BoxAssessmentBundle, BoxItemInput
from cosmin_assistant.models import StableId

BOX_5_MEASUREMENT_PROPERTY = "cross_cultural_validity_measurement_invariance"
BOX_5_KEY = "box_5_cross_cultural_validity_measurement_invariance"
BOX_5_ITEM_CODES = (
    "B5.1_translation_and_adaptation_quality",
    "B5.2_group_comparability",
    "B5.3_invariance_testing_method",
    "B5.4_sample_size_per_group",
    "B5.5_other_important_flaws",
)


def assess_box5_cross_cultural_validity_measurement_invariance(
    *,
    study_id: StableId,
    instrument_id: StableId,
    item_inputs: tuple[BoxItemInput, ...],
) -> BoxAssessmentBundle:
    """Assess COSMIN RoB Box 5 using explicit item ratings and evidence links."""

    item_assessments = build_item_assessments_for_box(
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=BOX_5_MEASUREMENT_PROPERTY,
        cosmin_box=BOX_5_KEY,
        item_inputs=item_inputs,
        expected_item_codes=BOX_5_ITEM_CODES,
    )
    return aggregate_box_assessment(
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=BOX_5_MEASUREMENT_PROPERTY,
        cosmin_box=BOX_5_KEY,
        item_assessments=item_assessments,
    )
