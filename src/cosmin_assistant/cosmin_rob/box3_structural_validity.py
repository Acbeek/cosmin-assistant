"""Initial COSMIN RoB Box 3 (Structural validity) assessment module."""

from __future__ import annotations

from cosmin_assistant.cosmin_rob.aggregation import aggregate_box_assessment
from cosmin_assistant.cosmin_rob.item_utils import build_item_assessments_for_box
from cosmin_assistant.cosmin_rob.models import BoxAssessmentBundle, BoxItemInput
from cosmin_assistant.models import StableId

BOX_3_MEASUREMENT_PROPERTY = "structural_validity"
BOX_3_KEY = "box_3_structural_validity"
BOX_3_ITEM_CODES = (
    "B3.1_ctt_factor_analysis_performed",
    "B3.2_irt_or_rasch_model_fit",
    "B3.3_sample_size_adequacy",
    "B3.4_other_important_flaws",
)


def assess_box3_structural_validity(
    *,
    study_id: StableId,
    instrument_id: StableId,
    item_inputs: tuple[BoxItemInput, ...],
) -> BoxAssessmentBundle:
    """Assess COSMIN RoB Box 3 using explicit item ratings and evidence links."""

    item_assessments = build_item_assessments_for_box(
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=BOX_3_MEASUREMENT_PROPERTY,
        cosmin_box=BOX_3_KEY,
        item_inputs=item_inputs,
        expected_item_codes=BOX_3_ITEM_CODES,
    )
    return aggregate_box_assessment(
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=BOX_3_MEASUREMENT_PROPERTY,
        cosmin_box=BOX_3_KEY,
        item_assessments=item_assessments,
    )
