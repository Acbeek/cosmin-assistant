"""Shared deterministic helpers for measurement-property rating modules."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from cosmin_assistant.extract.statistics_models import (
    EvidenceSourceType,
    StatisticCandidate,
    StatisticType,
)
from cosmin_assistant.measurement_rating.models import (
    PrerequisiteDecision,
    PrerequisiteStatus,
    RawResultRecord,
    ThresholdComparison,
)
from cosmin_assistant.models import (
    MeasurementPropertyRating,
    ProfileType,
    ReviewerDecisionStatus,
    StableId,
    UncertaintyStatus,
)
from cosmin_assistant.profiles import get_profile
from cosmin_assistant.profiles.base import BaseProfile


def stable_id(prefix: str, *parts: object) -> StableId:
    """Build deterministic IDs for rating artifacts."""

    serialized = "|".join(str(part) for part in parts)
    digest = hashlib.sha1(f"{prefix}|{serialized}".encode()).hexdigest()[:16]
    return f"{prefix}.{digest}"


def select_statistics(
    candidates: tuple[StatisticCandidate, ...],
    statistic_types: tuple[StatisticType, ...],
    *,
    allow_non_direct: bool = False,
) -> tuple[StatisticCandidate, ...]:
    """Return candidates matching requested statistic types in original order."""

    allowed = set(statistic_types)
    return tuple(
        candidate
        for candidate in candidates
        if candidate.statistic_type in allowed
        and (
            allow_non_direct
            or (
                candidate.evidence_source is EvidenceSourceType.CURRENT_STUDY
                and candidate.supports_direct_assessment
            )
        )
    )


def to_raw_result_records(
    candidates: tuple[StatisticCandidate, ...],
) -> tuple[RawResultRecord, ...]:
    """Convert extracted statistic candidates into auditable raw result records."""

    return tuple(
        RawResultRecord(
            statistic_type=candidate.statistic_type,
            value_raw=candidate.value_raw,
            value_normalized=candidate.value_normalized,
            subgroup_label=candidate.subgroup_label,
            evidence_span_ids=candidate.evidence_span_ids,
            evidence_source=candidate.evidence_source,
            supports_direct_assessment=candidate.supports_direct_assessment,
            measurement_property_routes=candidate.measurement_property_routes,
            instrument_name_hints=candidate.instrument_name_hints,
            comparator_instrument_hints=candidate.comparator_instrument_hints,
            provenance_flags=_provenance_flags(candidate),
        )
        for candidate in candidates
    )


def _provenance_flags(candidate: StatisticCandidate) -> tuple[str, ...]:
    flags: list[str] = [candidate.evidence_source.value]
    if candidate.supports_direct_assessment:
        flags.append("supports_direct_assessment")
    else:
        flags.append("not_directly_assessable")
    if candidate.comparator_instrument_hints:
        flags.append("comparator_instrument_context")
    return tuple(flags)


def merge_evidence_span_ids(
    raw_results: tuple[RawResultRecord, ...],
    threshold_comparisons: tuple[ThresholdComparison, ...],
    prerequisite_evidence_span_ids: Iterable[StableId] = (),
) -> tuple[StableId, ...]:
    """Return sorted unique evidence span IDs from all relevant rating inputs."""

    merged: set[StableId] = set(prerequisite_evidence_span_ids)
    for raw in raw_results:
        merged.update(raw.evidence_span_ids)
    for comparison in threshold_comparisons:
        merged.update(comparison.evidence_span_ids)
    return tuple(sorted(merged))


def outcome_flags(
    rating: MeasurementPropertyRating,
) -> tuple[bool, bool]:
    """Return tuple of presence flags for sufficient/insufficient outcomes."""

    return (
        rating is MeasurementPropertyRating.SUFFICIENT,
        rating is MeasurementPropertyRating.INSUFFICIENT,
    )


def derive_status_from_rating(
    rating: MeasurementPropertyRating,
) -> tuple[UncertaintyStatus, ReviewerDecisionStatus]:
    """Map computed rating into default uncertainty and reviewer decision statuses."""

    if rating is MeasurementPropertyRating.INCONSISTENT:
        return (UncertaintyStatus.CONFLICTING, ReviewerDecisionStatus.PENDING)

    if rating is MeasurementPropertyRating.INDETERMINATE:
        return (UncertaintyStatus.MISSING_EVIDENCE, ReviewerDecisionStatus.PENDING)

    return (UncertaintyStatus.CERTAIN, ReviewerDecisionStatus.NOT_REQUIRED)


def resolve_profile(profile_type: ProfileType | str) -> tuple[ProfileType, BaseProfile]:
    """Resolve profile input into enum value and profile metadata instance."""

    resolved_type = ProfileType(profile_type)
    return resolved_type, get_profile(resolved_type)


def resolve_named_prerequisite(
    *,
    decisions: tuple[PrerequisiteDecision, ...],
    name: str,
    missing_detail: str,
) -> PrerequisiteDecision:
    """Resolve one prerequisite decision by name with conflict/missing handling."""

    matches = [decision for decision in decisions if decision.name == name]
    if not matches:
        return PrerequisiteDecision(
            name=name,
            status=PrerequisiteStatus.MISSING,
            detail=missing_detail,
        )

    unique_statuses = {decision.status for decision in matches}
    if len(unique_statuses) > 1:
        span_ids = tuple(
            sorted({span for decision in matches for span in decision.evidence_span_ids})
        )
        return PrerequisiteDecision(
            name=name,
            status=PrerequisiteStatus.MISSING,
            detail="Conflicting prerequisite decisions were provided.",
            evidence_span_ids=span_ids,
        )

    chosen = matches[0]
    return PrerequisiteDecision(
        name=chosen.name,
        status=chosen.status,
        detail=chosen.detail,
        evidence_span_ids=chosen.evidence_span_ids,
    )
