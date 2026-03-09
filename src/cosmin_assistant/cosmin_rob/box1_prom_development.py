"""COSMIN RoB Box 1 (PROM development).

This box is intentionally reviewer-in-the-loop. The module does not infer
item ratings from extracted text; it only structures explicit item judgments
and applies deterministic worst-score-counts aggregation.
"""

from __future__ import annotations

from cosmin_assistant.cosmin_rob.aggregation import aggregate_box_assessment
from cosmin_assistant.cosmin_rob.item_utils import build_item_assessments_for_box
from cosmin_assistant.cosmin_rob.models import BoxAssessmentBundle, BoxItemInput
from cosmin_assistant.models import StableId

BOX_1_MEASUREMENT_PROPERTY = "prom_development"
BOX_1_KEY = "box_1_prom_development"
BOX_1_ITEM_CODES = (
    "B1.1_target_population_definition",
    "B1.2_concept_elicitation_methods",
    "B1.3_item_generation_transparency",
    "B1.4_cognitive_interviewing_or_pilot_testing",
    "B1.5_other_important_flaws",
)


def assess_box1_prom_development(
    *,
    study_id: StableId,
    instrument_id: StableId,
    item_inputs: tuple[BoxItemInput, ...],
) -> BoxAssessmentBundle:
    """Assess COSMIN RoB Box 1 using explicit item ratings and evidence links."""

    item_assessments = build_item_assessments_for_box(
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=BOX_1_MEASUREMENT_PROPERTY,
        cosmin_box=BOX_1_KEY,
        item_inputs=item_inputs,
        expected_item_codes=BOX_1_ITEM_CODES,
    )
    return aggregate_box_assessment(
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=BOX_1_MEASUREMENT_PROPERTY,
        cosmin_box=BOX_1_KEY,
        item_assessments=item_assessments,
    )
