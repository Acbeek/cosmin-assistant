"""COSMIN RoB Box 2 (Content validity).

Content-validity appraisal is conservatively reviewer-in-the-loop. This
module intentionally avoids auto-scoring and only aggregates explicit,
evidence-linked item ratings.
"""

from __future__ import annotations

from cosmin_assistant.cosmin_rob.aggregation import aggregate_box_assessment
from cosmin_assistant.cosmin_rob.item_utils import build_item_assessments_for_box
from cosmin_assistant.cosmin_rob.models import BoxAssessmentBundle, BoxItemInput
from cosmin_assistant.models import StableId

BOX_2_MEASUREMENT_PROPERTY = "content_validity"
BOX_2_KEY = "box_2_content_validity"
BOX_2_ITEM_CODES = (
    "B2.1_relevance_to_construct",
    "B2.2_relevance_to_target_population",
    "B2.3_relevance_to_context_of_use",
    "B2.4_comprehensiveness_of_items",
    "B2.5_comprehensibility_of_items",
    "B2.6_other_important_flaws",
)


def assess_box2_content_validity(
    *,
    study_id: StableId,
    instrument_id: StableId,
    item_inputs: tuple[BoxItemInput, ...],
) -> BoxAssessmentBundle:
    """Assess COSMIN RoB Box 2 using explicit item ratings and evidence links."""

    item_assessments = build_item_assessments_for_box(
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=BOX_2_MEASUREMENT_PROPERTY,
        cosmin_box=BOX_2_KEY,
        item_inputs=item_inputs,
        expected_item_codes=BOX_2_ITEM_CODES,
    )
    return aggregate_box_assessment(
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=BOX_2_MEASUREMENT_PROPERTY,
        cosmin_box=BOX_2_KEY,
        item_assessments=item_assessments,
    )
