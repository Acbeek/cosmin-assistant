"""Initial COSMIN RoB Box 4 (Internal consistency) assessment module."""

from __future__ import annotations

from cosmin_assistant.cosmin_rob.aggregation import aggregate_box_assessment
from cosmin_assistant.cosmin_rob.item_utils import build_item_assessments_for_box
from cosmin_assistant.cosmin_rob.models import BoxAssessmentBundle, BoxItemInput
from cosmin_assistant.models import StableId

BOX_4_MEASUREMENT_PROPERTY = "internal_consistency"
BOX_4_KEY = "box_4_internal_consistency"
BOX_4_ITEM_CODES = (
    "B4.1_continuous_scores_alpha_or_omega",
    "B4.2_dichotomous_scores_alpha_or_kr20",
    "B4.3_irt_scores_se_theta_or_reliability",
    "B4.4_other_important_flaws",
)


def assess_box4_internal_consistency(
    *,
    study_id: StableId,
    instrument_id: StableId,
    item_inputs: tuple[BoxItemInput, ...],
) -> BoxAssessmentBundle:
    """Assess COSMIN RoB Box 4 using explicit item ratings and evidence links."""

    item_assessments = build_item_assessments_for_box(
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=BOX_4_MEASUREMENT_PROPERTY,
        cosmin_box=BOX_4_KEY,
        item_inputs=item_inputs,
        expected_item_codes=BOX_4_ITEM_CODES,
    )
    return aggregate_box_assessment(
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=BOX_4_MEASUREMENT_PROPERTY,
        cosmin_box=BOX_4_KEY,
        item_assessments=item_assessments,
    )
