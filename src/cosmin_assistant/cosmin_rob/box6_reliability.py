"""Initial COSMIN RoB Box 6 (Reliability) assessment module."""

from __future__ import annotations

from cosmin_assistant.cosmin_rob.aggregation import aggregate_box_assessment
from cosmin_assistant.cosmin_rob.item_utils import build_item_assessments_for_box
from cosmin_assistant.cosmin_rob.models import BoxAssessmentBundle, BoxItemInput
from cosmin_assistant.models import StableId

BOX_6_MEASUREMENT_PROPERTY = "reliability"
BOX_6_KEY = "box_6_reliability"
BOX_6_ITEM_CODES = (
    "B6.1_stability_of_patients",
    "B6.2_time_interval_appropriateness",
    "B6.3_measurement_conditions_similarity",
    "B6.4_appropriate_icc_for_continuous_scores",
    "B6.5_kappa_for_dichotomous_scores",
    "B6.6_unweighted_kappa_for_nominal_scores",
    "B6.7_weighted_kappa_for_ordinal_scores",
    "B6.8_other_important_flaws",
)


def assess_box6_reliability(
    *,
    study_id: StableId,
    instrument_id: StableId,
    item_inputs: tuple[BoxItemInput, ...],
) -> BoxAssessmentBundle:
    """Assess COSMIN RoB Box 6 using explicit item ratings and evidence links."""

    item_assessments = build_item_assessments_for_box(
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=BOX_6_MEASUREMENT_PROPERTY,
        cosmin_box=BOX_6_KEY,
        item_inputs=item_inputs,
        expected_item_codes=BOX_6_ITEM_CODES,
    )
    return aggregate_box_assessment(
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=BOX_6_MEASUREMENT_PROPERTY,
        cosmin_box=BOX_6_KEY,
        item_assessments=item_assessments,
    )
