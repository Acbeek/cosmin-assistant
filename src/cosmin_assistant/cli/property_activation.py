"""Scientific eligibility gate models and deterministic helpers."""

from __future__ import annotations

import hashlib

from cosmin_assistant.extract import StatisticCandidate
from cosmin_assistant.models import (
    InstrumentType,
    ModelBase,
    NonEmptyText,
    PropertyActivationStatus,
    StableId,
)

STEP6_PROM_ITEM_BASED_PROPERTIES: tuple[str, ...] = (
    "structural_validity",
    "internal_consistency",
    "cross_cultural_validity_measurement_invariance",
)


class PropertyActivationDecision(ModelBase):
    """Eligibility/activation decision before COSMIN box and rating execution."""

    id: StableId
    study_id: StableId
    instrument_id: StableId
    instrument_name: NonEmptyText
    instrument_type: InstrumentType
    measurement_property: NonEmptyText
    activation_status: PropertyActivationStatus
    explanation: NonEmptyText
    evidence_span_ids: tuple[StableId, ...] = ()
    rating_input_source_flags: tuple[str, ...] = ()


def stable_activation_id(prefix: str, *parts: object) -> StableId:
    """Build deterministic IDs for property-activation artifacts."""

    serialized = "|".join(str(part) for part in parts)
    digest = hashlib.sha1(f"{prefix}|{serialized}".encode()).hexdigest()[:16]
    return f"{prefix}.{digest}"


def candidate_source_flags(candidates: tuple[StatisticCandidate, ...]) -> tuple[str, ...]:
    """Summarize routing/provenance source flags from selected candidates."""

    flags: set[str] = set()
    for candidate in candidates:
        flags.add(candidate.evidence_source.value)
        if candidate.comparator_instrument_hints:
            flags.add("comparator_instrument_context")
        if candidate.supports_direct_assessment:
            flags.add("supports_direct_assessment")
        else:
            flags.add("not_directly_assessable")
    return tuple(sorted(flags))


def merged_candidate_evidence(candidates: tuple[StatisticCandidate, ...]) -> tuple[StableId, ...]:
    """Collect sorted unique evidence span IDs from candidates."""

    return tuple(
        sorted({span_id for candidate in candidates for span_id in candidate.evidence_span_ids})
    )
