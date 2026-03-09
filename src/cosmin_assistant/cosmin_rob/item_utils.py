"""Common utilities for deterministic COSMIN item assessment construction."""

from __future__ import annotations

import hashlib

from cosmin_assistant.cosmin_rob.models import BoxItemInput
from cosmin_assistant.models import (
    CosminItemAssessment,
    NonEmptyText,
    StableId,
)


def build_item_assessments_for_box(
    *,
    study_id: StableId,
    instrument_id: StableId,
    measurement_property: NonEmptyText,
    cosmin_box: NonEmptyText,
    item_inputs: tuple[BoxItemInput, ...],
    expected_item_codes: tuple[str, ...],
) -> tuple[CosminItemAssessment, ...]:
    """Build deterministic item assessments for one COSMIN box.

    All expected item codes must be present to keep NA handling explicit.
    Non-applicable items should therefore be provided with
    ``item_rating=CosminItemRating.NOT_APPLICABLE`` rather than omitted.
    """

    _validate_item_coverage(item_inputs, expected_item_codes)

    return tuple(
        build_item_assessment(
            study_id=study_id,
            instrument_id=instrument_id,
            measurement_property=measurement_property,
            cosmin_box=cosmin_box,
            item_input=item_input,
        )
        for item_input in item_inputs
    )


def build_item_assessment(
    *,
    study_id: StableId,
    instrument_id: StableId,
    measurement_property: NonEmptyText,
    cosmin_box: NonEmptyText,
    item_input: BoxItemInput,
) -> CosminItemAssessment:
    """Build one deterministic COSMIN item assessment from a typed input."""

    evidence_key = ",".join(item_input.evidence_span_ids)
    item_id = _stable_id(
        "rob.item",
        study_id,
        instrument_id,
        measurement_property,
        cosmin_box,
        item_input.item_code,
        item_input.item_rating.value,
        evidence_key,
    )
    return CosminItemAssessment(
        id=item_id,
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=measurement_property,
        cosmin_box=cosmin_box,
        item_code=item_input.item_code,
        item_rating=item_input.item_rating,
        evidence_span_ids=list(item_input.evidence_span_ids),
        uncertainty_status=item_input.uncertainty_status,
        reviewer_decision_status=item_input.reviewer_decision_status,
    )


def _validate_item_coverage(
    item_inputs: tuple[BoxItemInput, ...],
    expected_item_codes: tuple[str, ...],
) -> None:
    expected = set(expected_item_codes)
    provided_codes = [item.item_code for item in item_inputs]
    provided = set(provided_codes)

    if len(provided_codes) != len(provided):
        msg = "duplicate item_code values are not allowed"
        raise ValueError(msg)

    missing = expected - provided
    unexpected = provided - expected

    if missing or unexpected:
        missing_str = ", ".join(sorted(missing)) or "-"
        unexpected_str = ", ".join(sorted(unexpected)) or "-"
        msg = (
            "item coverage mismatch for box assessment. "
            f"missing: [{missing_str}], unexpected: [{unexpected_str}]"
        )
        raise ValueError(msg)


def _stable_id(prefix: str, *parts: object) -> StableId:
    serialized = "|".join(str(part) for part in parts)
    digest = hashlib.sha1(f"{prefix}|{serialized}".encode()).hexdigest()[:16]
    return f"{prefix}.{digest}"
