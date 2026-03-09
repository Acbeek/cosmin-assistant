"""Structured COSMIN-style table builders (intermediate representations).

This module builds JSON/CSV-ready table objects and deliberately avoids
any direct dependency on Word/DOCX rendering.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any, TypeVar

import pandas as pd

from cosmin_assistant.cosmin_rob import BoxAssessmentBundle
from cosmin_assistant.extract import (
    ContextFieldExtraction,
    ContextValueCandidate,
    InstrumentContextExtractionResult,
    SampleSizeRole,
    StudyContextExtractionResult,
)
from cosmin_assistant.grade import ModifiedGradeResult
from cosmin_assistant.measurement_rating import MeasurementPropertyRatingResult, RawResultRecord
from cosmin_assistant.models import ModelBase
from cosmin_assistant.synthesize import SynthesisAggregateResult
from cosmin_assistant.tables.intermediate_models import (
    TableLegendEntry,
    Template5CharacteristicsRow,
    Template5CharacteristicsTable,
    Template7EvidenceRow,
    Template7EvidenceTable,
    Template7RowKind,
    Template8SummaryRow,
    Template8SummaryTable,
)

InstrumentKey = tuple[str, str | None, str | None]
_TableModelT = TypeVar(
    "_TableModelT",
    Template5CharacteristicsTable,
    Template7EvidenceTable,
    Template8SummaryTable,
)


def build_template5_characteristics_table(
    *,
    study_contexts: tuple[StudyContextExtractionResult, ...],
    instrument_contexts: tuple[InstrumentContextExtractionResult, ...],
) -> Template5CharacteristicsTable:
    """Build template 5 equivalent rows for study characteristics."""

    study_by_id = {context.study_id: context for context in study_contexts}
    grouped: dict[InstrumentKey, list[InstrumentContextExtractionResult]] = defaultdict(list)
    for context in instrument_contexts:
        grouped[_instrument_key_from_context(context)].append(context)

    rows: list[Template5CharacteristicsRow] = []
    for instrument_key in sorted(grouped.keys(), key=_instrument_key_sort):
        contexts = sorted(grouped[instrument_key], key=lambda item: (item.study_id, item.id))
        for index, context in enumerate(contexts, start=1):
            study = study_by_id.get(context.study_id)
            instrument_name, instrument_version, subscale = instrument_key
            rows.append(
                Template5CharacteristicsRow(
                    id=_stable_id(
                        "t5row",
                        instrument_name,
                        instrument_version or "",
                        subscale or "",
                        context.study_id,
                        index,
                    ),
                    instrument_name=instrument_name,
                    instrument_version=instrument_version,
                    subscale=subscale,
                    study_id=context.study_id,
                    study_order_within_instrument=index,
                    is_additional_study_row=index > 1,
                    study_design=_study_field_text(study, "study_design"),
                    target_population=_study_field_text(study, "target_population"),
                    language=_study_field_text(study, "language"),
                    country=_study_field_text(study, "country"),
                    enrollment_n=_sample_size_for_role(study, SampleSizeRole.ENROLLMENT),
                    analyzed_n=_sample_size_for_role(study, SampleSizeRole.ANALYZED),
                    limb_level_n=_sample_size_for_role(study, SampleSizeRole.LIMB_LEVEL),
                    follow_up_schedule=_study_field_text(study, "follow_up_schedule"),
                    measurement_properties_mentioned=_study_field_text(
                        study,
                        "measurement_properties_mentioned",
                    ),
                )
            )

    return Template5CharacteristicsTable(
        id=_stable_id("table", "template_5", len(rows)),
        rows=tuple(rows),
        legends=_template5_legends(),
    )


def build_template7_evidence_table(
    *,
    instrument_contexts: tuple[InstrumentContextExtractionResult, ...],
    rob_assessments: tuple[BoxAssessmentBundle, ...],
    measurement_results: tuple[MeasurementPropertyRatingResult, ...],
    synthesis_results: tuple[SynthesisAggregateResult, ...],
    grade_results: tuple[ModifiedGradeResult, ...],
    measurement_properties_universe: tuple[str, ...] | None = None,
) -> Template7EvidenceTable:
    """Build template 7 equivalent rows with study and summary levels."""

    instrument_key_by_id = _instrument_key_by_id(instrument_contexts)
    grouped_results: dict[tuple[InstrumentKey, str], list[MeasurementPropertyRatingResult]] = (
        defaultdict(list)
    )
    instrument_keys: set[InstrumentKey] = set(_instrument_keys_from_contexts(instrument_contexts))

    for result in measurement_results:
        instrument_key = _instrument_key_from_result(result, instrument_key_by_id)
        grouped_results[(instrument_key, result.measurement_property)].append(result)
        instrument_keys.add(instrument_key)

    synthesis_map = _synthesis_map(synthesis_results)
    for instrument_key, _property in synthesis_map:
        instrument_keys.add(instrument_key)

    rob_map = _rob_map(rob_assessments)
    grade_map = {result.synthesis_id: result for result in grade_results}

    rows: list[Template7EvidenceRow] = []
    for instrument_key in sorted(instrument_keys, key=_instrument_key_sort):
        property_order = _measurement_property_order(
            instrument_key=instrument_key,
            grouped_results=grouped_results,
            synthesis_map=synthesis_map,
            measurement_properties_universe=measurement_properties_universe,
        )
        for measurement_property in property_order:
            study_rows = sorted(
                grouped_results.get((instrument_key, measurement_property), []),
                key=lambda item: (item.study_id, item.id),
            )
            for index, result in enumerate(study_rows, start=1):
                rows.append(
                    Template7EvidenceRow(
                        id=_stable_id(
                            "t7row",
                            "study",
                            instrument_key[0],
                            instrument_key[1] or "",
                            instrument_key[2] or "",
                            measurement_property,
                            result.study_id,
                            index,
                        ),
                        row_kind=Template7RowKind.STUDY,
                        instrument_name=instrument_key[0],
                        instrument_version=instrument_key[1],
                        subscale=instrument_key[2],
                        measurement_property=measurement_property,
                        study_id=result.study_id,
                        study_order_within_instrument_property=index,
                        is_additional_study_row=index > 1,
                        per_study_rob=rob_map.get(
                            (result.study_id, result.instrument_id, result.measurement_property)
                        ),
                        per_study_result=_raw_result_text(result.raw_results),
                        study_rating=result.computed_rating.value,
                    )
                )

            synthesis = synthesis_map.get((instrument_key, measurement_property))
            grade = grade_map.get(synthesis.id) if synthesis is not None else None
            rows.append(
                Template7EvidenceRow(
                    id=_stable_id(
                        "t7row",
                        "summary",
                        instrument_key[0],
                        instrument_key[1] or "",
                        instrument_key[2] or "",
                        measurement_property,
                    ),
                    row_kind=Template7RowKind.SUMMARY,
                    instrument_name=instrument_key[0],
                    instrument_version=instrument_key[1],
                    subscale=instrument_key[2],
                    measurement_property=measurement_property,
                    summarized_result=(
                        synthesis.summary_explanation if synthesis is not None else None
                    ),
                    overall_rating=(
                        synthesis.summary_rating.value if synthesis is not None else None
                    ),
                    certainty_of_evidence=(
                        grade.final_certainty.value if grade is not None else None
                    ),
                    total_sample_size=(
                        synthesis.total_sample_size if synthesis is not None else None
                    ),
                )
            )

    return Template7EvidenceTable(
        id=_stable_id("table", "template_7", len(rows)),
        rows=tuple(rows),
        legends=_template7_legends(),
    )


def build_template8_summary_table(
    *,
    instrument_contexts: tuple[InstrumentContextExtractionResult, ...],
    synthesis_results: tuple[SynthesisAggregateResult, ...],
    grade_results: tuple[ModifiedGradeResult, ...],
    measurement_properties_universe: tuple[str, ...] | None = None,
) -> Template8SummaryTable:
    """Build template 8 equivalent summary rows by instrument and property."""

    instrument_keys: set[InstrumentKey] = set(_instrument_keys_from_contexts(instrument_contexts))
    synthesis_map = _synthesis_map(synthesis_results)
    for instrument_key, _property in synthesis_map:
        instrument_keys.add(instrument_key)

    grade_map = {result.synthesis_id: result for result in grade_results}

    rows: list[Template8SummaryRow] = []
    for instrument_key in sorted(instrument_keys, key=_instrument_key_sort):
        property_order = _summary_property_order(
            instrument_key=instrument_key,
            synthesis_map=synthesis_map,
            measurement_properties_universe=measurement_properties_universe,
        )
        for measurement_property in property_order:
            synthesis = synthesis_map.get((instrument_key, measurement_property))
            grade = grade_map.get(synthesis.id) if synthesis is not None else None

            rows.append(
                Template8SummaryRow(
                    id=_stable_id(
                        "t8row",
                        instrument_key[0],
                        instrument_key[1] or "",
                        instrument_key[2] or "",
                        measurement_property,
                    ),
                    instrument_name=instrument_key[0],
                    instrument_version=instrument_key[1],
                    subscale=instrument_key[2],
                    measurement_property=measurement_property,
                    summarized_result=(
                        synthesis.summary_explanation if synthesis is not None else None
                    ),
                    overall_rating=(
                        synthesis.summary_rating.value if synthesis is not None else None
                    ),
                    certainty_of_evidence=(
                        grade.final_certainty.value if grade is not None else None
                    ),
                    total_sample_size=(
                        synthesis.total_sample_size if synthesis is not None else None
                    ),
                    inconsistent_findings=(
                        synthesis.inconsistent_findings if synthesis is not None else None
                    ),
                )
            )

    return Template8SummaryTable(
        id=_stable_id("table", "template_8", len(rows)),
        rows=tuple(rows),
        legends=_template8_legends(),
    )


def template5_to_dataframe(table: Template5CharacteristicsTable) -> pd.DataFrame:
    """Convert template 5 table rows to a CSV-ready data frame."""

    return _rows_to_dataframe(table.rows)


def template7_to_dataframe(table: Template7EvidenceTable) -> pd.DataFrame:
    """Convert template 7 table rows to a CSV-ready data frame."""

    return _rows_to_dataframe(table.rows)


def template8_to_dataframe(table: Template8SummaryTable) -> pd.DataFrame:
    """Convert template 8 table rows to a CSV-ready data frame."""

    return _rows_to_dataframe(table.rows)


def table_to_json_ready(table: _TableModelT) -> dict[str, Any]:
    """Convert any intermediate table object to JSON-ready dictionary."""

    return table.model_dump(mode="json")


def _rows_to_dataframe(rows: tuple[ModelBase, ...]) -> pd.DataFrame:
    payload = [row.model_dump(mode="json") for row in rows]
    return pd.DataFrame(payload)


def _instrument_keys_from_contexts(
    instrument_contexts: tuple[InstrumentContextExtractionResult, ...],
) -> tuple[InstrumentKey, ...]:
    seen: dict[InstrumentKey, None] = {}
    for context in instrument_contexts:
        seen[_instrument_key_from_context(context)] = None
    return tuple(seen.keys())


def _instrument_key_by_id(
    instrument_contexts: tuple[InstrumentContextExtractionResult, ...],
) -> dict[str, InstrumentKey]:
    mapping: dict[str, InstrumentKey] = {}
    for context in sorted(instrument_contexts, key=lambda item: item.id):
        mapping.setdefault(context.instrument_id, _instrument_key_from_context(context))
    return mapping


def _instrument_key_from_context(context: InstrumentContextExtractionResult) -> InstrumentKey:
    instrument_name = _field_text(context.instrument_name) or f"instrument:{context.instrument_id}"
    return (
        instrument_name,
        _field_text(context.instrument_version),
        _field_text(context.subscale),
    )


def _instrument_key_from_result(
    result: MeasurementPropertyRatingResult,
    instrument_key_by_id: dict[str, InstrumentKey],
) -> InstrumentKey:
    fallback_name = f"instrument:{result.instrument_id}"
    return instrument_key_by_id.get(result.instrument_id, (fallback_name, None, None))


def _instrument_key_sort(item: InstrumentKey) -> tuple[str, str, str]:
    return (item[0].lower(), (item[1] or "").lower(), (item[2] or "").lower())


def _measurement_property_order(
    *,
    instrument_key: InstrumentKey,
    grouped_results: dict[tuple[InstrumentKey, str], list[MeasurementPropertyRatingResult]],
    synthesis_map: dict[tuple[InstrumentKey, str], SynthesisAggregateResult],
    measurement_properties_universe: tuple[str, ...] | None,
) -> tuple[str, ...]:
    if measurement_properties_universe is not None:
        return measurement_properties_universe

    observed: set[str] = set()
    for key, measurement_property in grouped_results:
        if key == instrument_key:
            observed.add(measurement_property)
    for key, measurement_property in synthesis_map:
        if key == instrument_key:
            observed.add(measurement_property)
    return tuple(sorted(observed))


def _summary_property_order(
    *,
    instrument_key: InstrumentKey,
    synthesis_map: dict[tuple[InstrumentKey, str], SynthesisAggregateResult],
    measurement_properties_universe: tuple[str, ...] | None,
) -> tuple[str, ...]:
    if measurement_properties_universe is not None:
        return measurement_properties_universe

    observed = {
        measurement_property for key, measurement_property in synthesis_map if key == instrument_key
    }
    return tuple(sorted(observed))


def _rob_map(
    rob_assessments: tuple[BoxAssessmentBundle, ...],
) -> dict[tuple[str, str, str], str]:
    mapping: dict[tuple[str, str, str], str] = {}
    for bundle in sorted(rob_assessments, key=lambda item: item.id):
        box = bundle.box_assessment
        key = (box.study_id, box.instrument_id, box.measurement_property)
        mapping.setdefault(key, box.box_rating.value)
    return mapping


def _synthesis_map(
    synthesis_results: tuple[SynthesisAggregateResult, ...],
) -> dict[tuple[InstrumentKey, str], SynthesisAggregateResult]:
    mapping: dict[tuple[InstrumentKey, str], SynthesisAggregateResult] = {}
    for result in sorted(synthesis_results, key=lambda item: item.id):
        key = (
            (result.instrument_name, result.instrument_version, result.subscale),
            result.measurement_property,
        )
        mapping.setdefault(key, result)
    return mapping


def _study_field_text(
    study: StudyContextExtractionResult | None,
    field_name: str,
) -> str | None:
    if study is None:
        return None
    field = getattr(study, field_name, None)
    if isinstance(field, ContextFieldExtraction):
        return _field_text(field)
    return None


def _sample_size_for_role(
    study: StudyContextExtractionResult | None,
    role: SampleSizeRole,
) -> int | None:
    if study is None:
        return None
    observations = sorted(study.sample_size_observations, key=lambda item: item.id)
    for observation in observations:
        if observation.role is role:
            return observation.sample_size_normalized
    return None


def _raw_result_text(raw_results: tuple[RawResultRecord, ...]) -> str | None:
    if not raw_results:
        return None
    parts: list[str] = []
    for record in raw_results:
        stat = record.statistic_type.value
        subgroup = f"[{record.subgroup_label}]" if record.subgroup_label else ""
        parts.append(f"{stat}{subgroup}={record.value_raw}")
    return "; ".join(parts)


def _field_text(field: ContextFieldExtraction) -> str | None:
    values = [_candidate_value_text(candidate) for candidate in field.candidates]
    deduped: list[str] = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    if not deduped:
        return None
    return " | ".join(deduped)


def _candidate_value_text(candidate: ContextValueCandidate) -> str:
    value = candidate.normalized_value
    if isinstance(value, tuple):
        return ", ".join(str(item) for item in value)
    if value is None:
        return candidate.raw_text
    return str(value)


def _template5_legends() -> tuple[TableLegendEntry, ...]:
    return (
        TableLegendEntry(
            key="additional_study_row",
            description="Rows below the first instrument row are additional study reports.",
        ),
        TableLegendEntry(
            key="blank_or_na",
            description="Blank/NA fields indicate not assessed or not reported.",
        ),
    )


def _template7_legends() -> tuple[TableLegendEntry, ...]:
    return (
        TableLegendEntry(key="study", description="Per-study evidence row."),
        TableLegendEntry(key="summary", description="Synthesis summary row."),
        TableLegendEntry(key="+", description="Sufficient."),
        TableLegendEntry(key="-", description="Insufficient."),
        TableLegendEntry(key="?", description="Indeterminate."),
        TableLegendEntry(key="±", description="Inconsistent findings."),
        TableLegendEntry(
            key="blank_or_na",
            description="Blank/NA fields indicate not assessed or unavailable evidence.",
        ),
    )


def _template8_legends() -> tuple[TableLegendEntry, ...]:
    return (
        TableLegendEntry(key="+", description="Sufficient."),
        TableLegendEntry(key="-", description="Insufficient."),
        TableLegendEntry(key="?", description="Indeterminate."),
        TableLegendEntry(key="±", description="Inconsistent findings."),
        TableLegendEntry(
            key="certainty_levels",
            description="high, moderate, low, very_low (modified GRADE).",
        ),
        TableLegendEntry(
            key="blank_or_na",
            description="Blank/NA fields indicate not assessed or unavailable evidence.",
        ),
    )


def _stable_id(prefix: str, *parts: object) -> str:
    serialized = "|".join(str(part) for part in parts)
    digest = hashlib.sha1(f"{prefix}|{serialized}".encode()).hexdigest()[:16]
    return f"{prefix}.{digest}"
