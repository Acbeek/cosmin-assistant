"""Deterministic first-pass synthesis logic."""

from __future__ import annotations

import hashlib
from collections import defaultdict

from cosmin_assistant.models import MeasurementPropertyRating, ReviewerDecisionStatus, StableId
from cosmin_assistant.synthesize.models import (
    StudySynthesisInput,
    SubgroupExplanationPlaceholder,
    SynthesisAggregateResult,
)


def synthesize_first_pass(
    study_results: tuple[StudySynthesisInput, ...],
) -> tuple[SynthesisAggregateResult, ...]:
    """Synthesize study-level results by instrument version/subscale and property."""

    if not study_results:
        return ()

    grouped: dict[
        tuple[str, str | None, str | None, str],
        list[StudySynthesisInput],
    ] = defaultdict(list)

    for result in study_results:
        key = (
            result.instrument_name,
            result.instrument_version,
            result.subscale,
            result.measurement_property,
        )
        grouped[key].append(result)

    outputs: list[SynthesisAggregateResult] = []
    for key in sorted(grouped):
        instrument_name, instrument_version, subscale, measurement_property = key
        entries = tuple(sorted(grouped[key], key=lambda item: (item.study_id, item.id)))

        summary_rating = _summarize_ratings(tuple(item.rating for item in entries))
        inconsistent = summary_rating is MeasurementPropertyRating.INCONSISTENT
        requires_subgroup_explanation = inconsistent
        total_sample_size = _sum_sample_sizes(entries)
        placeholders = _build_subgroup_placeholders(entries)
        evidence_span_ids = tuple(
            sorted({span_id for entry in entries for span_id in entry.evidence_span_ids})
        )

        outputs.append(
            SynthesisAggregateResult(
                id=_stable_id(
                    "syn",
                    instrument_name,
                    instrument_version or "",
                    subscale or "",
                    measurement_property,
                    ",".join(entry.id for entry in entries),
                ),
                instrument_name=instrument_name,
                instrument_version=instrument_version,
                subscale=subscale,
                measurement_property=measurement_property,
                summary_rating=summary_rating,
                summary_explanation=_summary_explanation(summary_rating),
                inconsistent_findings=inconsistent,
                requires_subgroup_explanation=requires_subgroup_explanation,
                total_sample_size=total_sample_size,
                study_entries=entries,
                subgroup_explanation_placeholders=placeholders,
                evidence_span_ids=evidence_span_ids,
            )
        )

    return tuple(outputs)


def _summarize_ratings(
    ratings: tuple[MeasurementPropertyRating, ...],
) -> MeasurementPropertyRating:
    unique = set(ratings)

    if MeasurementPropertyRating.INCONSISTENT in unique:
        return MeasurementPropertyRating.INCONSISTENT

    has_sufficient = MeasurementPropertyRating.SUFFICIENT in unique
    has_insufficient = MeasurementPropertyRating.INSUFFICIENT in unique
    has_indeterminate = MeasurementPropertyRating.INDETERMINATE in unique

    if has_sufficient and has_insufficient:
        return MeasurementPropertyRating.INCONSISTENT
    if has_sufficient and not has_insufficient and not has_indeterminate:
        return MeasurementPropertyRating.SUFFICIENT
    if has_insufficient and not has_sufficient and not has_indeterminate:
        return MeasurementPropertyRating.INSUFFICIENT
    if has_indeterminate and not has_sufficient and not has_insufficient:
        return MeasurementPropertyRating.INDETERMINATE

    return MeasurementPropertyRating.INDETERMINATE


def _sum_sample_sizes(entries: tuple[StudySynthesisInput, ...]) -> int | None:
    values = [entry.sample_size for entry in entries if entry.sample_size is not None]
    if not values:
        return None
    return sum(values)


def _build_subgroup_placeholders(
    entries: tuple[StudySynthesisInput, ...],
) -> tuple[SubgroupExplanationPlaceholder, ...]:
    labels = sorted(
        {
            entry.subgroup_label.strip()
            for entry in entries
            if entry.subgroup_label and entry.subgroup_label.strip()
        }
    )
    placeholders: list[SubgroupExplanationPlaceholder] = []
    for label in labels:
        evidence_span_ids = tuple(
            sorted(
                {
                    span_id
                    for entry in entries
                    if entry.subgroup_label == label
                    for span_id in entry.evidence_span_ids
                }
            )
        )
        placeholders.append(
            SubgroupExplanationPlaceholder(
                subgroup_label=label,
                explanation_status=ReviewerDecisionStatus.PENDING,
                explanation_text=None,
                evidence_span_ids=evidence_span_ids,
            )
        )
    return tuple(placeholders)


def _summary_explanation(rating: MeasurementPropertyRating) -> str:
    match rating:
        case MeasurementPropertyRating.SUFFICIENT:
            return "All included study-level results were sufficient."
        case MeasurementPropertyRating.INSUFFICIENT:
            return "All included study-level results were insufficient."
        case MeasurementPropertyRating.INCONSISTENT:
            return "Included study-level results were inconsistent (+ and - present)."
        case MeasurementPropertyRating.INDETERMINATE:
            return "Evidence was mixed with indeterminate results or otherwise insufficient."


def _stable_id(prefix: str, *parts: object) -> StableId:
    serialized = "|".join(str(part) for part in parts)
    digest = hashlib.sha1(f"{prefix}|{serialized}".encode()).hexdigest()[:16]
    return f"{prefix}.{digest}"
