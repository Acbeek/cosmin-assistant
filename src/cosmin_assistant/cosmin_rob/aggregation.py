"""Deterministic COSMIN box aggregation utilities."""

from __future__ import annotations

import hashlib

from cosmin_assistant.cosmin_rob.models import BoxAssessmentBundle
from cosmin_assistant.models import (
    CosminBoxAssessment,
    CosminBoxRating,
    CosminItemAssessment,
    CosminItemRating,
    NonEmptyText,
    ReviewerDecisionStatus,
    StableId,
    UncertaintyStatus,
)

WORST_SCORE_COUNTS_RULE = "ROB_WORST_SCORE_COUNTS_V1"
NA_HANDLING_RULE = "ROB_NA_EXCLUSION_V1"

_ITEM_RANK: dict[CosminItemRating, int] = {
    CosminItemRating.VERY_GOOD: 0,
    CosminItemRating.ADEQUATE: 1,
    CosminItemRating.DOUBTFUL: 2,
    CosminItemRating.INADEQUATE: 3,
}
_BOX_BY_RANK: dict[int, CosminBoxRating] = {
    0: CosminBoxRating.VERY_GOOD,
    1: CosminBoxRating.ADEQUATE,
    2: CosminBoxRating.DOUBTFUL,
    3: CosminBoxRating.INADEQUATE,
}


def aggregate_box_assessment(
    *,
    study_id: StableId,
    instrument_id: StableId,
    measurement_property: NonEmptyText,
    cosmin_box: NonEmptyText,
    item_assessments: tuple[CosminItemAssessment, ...],
) -> BoxAssessmentBundle:
    """Aggregate item-level assessments into a box-level COSMIN assessment.

    This applies worst-score-counts over applicable item ratings while
    excluding ``NOT_APPLICABLE`` item ratings from worst-score determination.
    """

    if not item_assessments:
        msg = "at least one item assessment is required for box aggregation"
        raise ValueError(msg)

    applicable_items = tuple(
        item for item in item_assessments if item.item_rating is not CosminItemRating.NOT_APPLICABLE
    )
    na_items = tuple(
        item for item in item_assessments if item.item_rating is CosminItemRating.NOT_APPLICABLE
    )

    box_rating: CosminBoxRating
    worst_items: tuple[CosminItemAssessment, ...]
    if not applicable_items:
        box_rating = CosminBoxRating.INDETERMINATE
        worst_items = tuple()
    else:
        worst_rank = max(_ITEM_RANK[item.item_rating] for item in applicable_items)
        box_rating = _BOX_BY_RANK[worst_rank]
        worst_items = tuple(
            item for item in applicable_items if _ITEM_RANK[item.item_rating] == worst_rank
        )

    uncertainty_status = _derive_box_uncertainty(applicable_items)
    reviewer_status = _derive_box_reviewer_status(applicable_items, uncertainty_status)

    evidence_span_ids = sorted(
        {span_id for item in item_assessments for span_id in item.evidence_span_ids}
    )
    box_assessment = CosminBoxAssessment(
        id=_stable_id(
            "rob.box",
            study_id,
            instrument_id,
            measurement_property,
            cosmin_box,
            box_rating.value,
            ",".join(item.id for item in item_assessments),
        ),
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=measurement_property,
        cosmin_box=cosmin_box,
        box_rating=box_rating,
        item_assessment_ids=[item.id for item in item_assessments],
        evidence_span_ids=evidence_span_ids,
        uncertainty_status=uncertainty_status,
        reviewer_decision_status=reviewer_status,
    )

    return BoxAssessmentBundle(
        id=_stable_id(
            "rob.bundle",
            box_assessment.id,
            ",".join(item.id for item in item_assessments),
        ),
        box_assessment=box_assessment,
        item_assessments=item_assessments,
        aggregation_rule=WORST_SCORE_COUNTS_RULE,
        na_handling_rule=NA_HANDLING_RULE,
        worst_score_counts_applied=True,
        applicable_item_assessment_ids=tuple(item.id for item in applicable_items),
        not_applicable_item_assessment_ids=tuple(item.id for item in na_items),
        worst_item_assessment_ids=tuple(item.id for item in worst_items),
    )


def _derive_box_uncertainty(
    applicable_items: tuple[CosminItemAssessment, ...],
) -> UncertaintyStatus:
    if not applicable_items:
        return UncertaintyStatus.MISSING_EVIDENCE

    if any(item.uncertainty_status is not UncertaintyStatus.CERTAIN for item in applicable_items):
        return UncertaintyStatus.REVIEWER_REQUIRED

    return UncertaintyStatus.CERTAIN


def _derive_box_reviewer_status(
    applicable_items: tuple[CosminItemAssessment, ...],
    uncertainty_status: UncertaintyStatus,
) -> ReviewerDecisionStatus:
    if not applicable_items or uncertainty_status is UncertaintyStatus.REVIEWER_REQUIRED:
        return ReviewerDecisionStatus.PENDING

    if any(
        item.reviewer_decision_status is not ReviewerDecisionStatus.NOT_REQUIRED
        for item in applicable_items
    ):
        return ReviewerDecisionStatus.PENDING

    return ReviewerDecisionStatus.NOT_REQUIRED


def _stable_id(prefix: str, *parts: object) -> StableId:
    serialized = "|".join(str(part) for part in parts)
    digest = hashlib.sha1(f"{prefix}|{serialized}".encode()).hexdigest()[:16]
    return f"{prefix}.{digest}"
