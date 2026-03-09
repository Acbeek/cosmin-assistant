"""Shared deterministic helpers for measurement-property rating modules."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from cosmin_assistant.extract.statistics_models import StatisticCandidate, StatisticType
from cosmin_assistant.measurement_rating.models import RawResultRecord, ThresholdComparison
from cosmin_assistant.models import (
    MeasurementPropertyRating,
    ReviewerDecisionStatus,
    StableId,
    UncertaintyStatus,
)


def stable_id(prefix: str, *parts: object) -> StableId:
    """Build deterministic IDs for rating artifacts."""

    serialized = "|".join(str(part) for part in parts)
    digest = hashlib.sha1(f"{prefix}|{serialized}".encode()).hexdigest()[:16]
    return f"{prefix}.{digest}"


def select_statistics(
    candidates: tuple[StatisticCandidate, ...],
    statistic_types: tuple[StatisticType, ...],
) -> tuple[StatisticCandidate, ...]:
    """Return candidates matching requested statistic types in original order."""

    allowed = set(statistic_types)
    return tuple(candidate for candidate in candidates if candidate.statistic_type in allowed)


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
        )
        for candidate in candidates
    )


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
