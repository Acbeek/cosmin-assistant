"""COSMIN RoB Box 10 (Responsiveness)."""

from __future__ import annotations

from cosmin_assistant.cosmin_rob.aggregation import aggregate_box_assessment
from cosmin_assistant.cosmin_rob.item_utils import build_item_assessments_for_box
from cosmin_assistant.cosmin_rob.models import BoxAssessmentBundle, BoxItemInput
from cosmin_assistant.models import StableId

BOX_10_MEASUREMENT_PROPERTY = "responsiveness"
BOX_10_KEY = "box_10_responsiveness"
BOX_10_ITEM_CODES = (
    "B10.1_hypotheses_predefined",
    "B10.2_stable_or_expected_change_groups",
    "B10.3_design_and_followup_appropriateness",
    "B10.4_statistical_analysis_appropriateness",
    "B10.5_other_important_flaws",
)


def assess_box10_responsiveness(
    *,
    study_id: StableId,
    instrument_id: StableId,
    item_inputs: tuple[BoxItemInput, ...],
) -> BoxAssessmentBundle:
    """Assess COSMIN RoB Box 10 using explicit item ratings and evidence links."""

    item_assessments = build_item_assessments_for_box(
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=BOX_10_MEASUREMENT_PROPERTY,
        cosmin_box=BOX_10_KEY,
        item_inputs=item_inputs,
        expected_item_codes=BOX_10_ITEM_CODES,
    )
    return aggregate_box_assessment(
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=BOX_10_MEASUREMENT_PROPERTY,
        cosmin_box=BOX_10_KEY,
        item_assessments=item_assessments,
    )
