"""Structured COSMIN-style table builders (intermediate representations).

This module builds JSON/CSV-ready table objects and deliberately avoids
any direct dependency on Word/DOCX rendering.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, TypeVar

import pandas as pd

from cosmin_assistant.cosmin_rob import BOX_1_KEY, BOX_2_KEY, BoxAssessmentBundle
from cosmin_assistant.extract import (
    ContextFieldExtraction,
    ContextValueCandidate,
    FieldDetectionStatus,
    InstrumentContextExtractionResult,
    InstrumentContextRole,
    SampleSizeRole,
    StudyContextExtractionResult,
)
from cosmin_assistant.grade import ModifiedGradeResult
from cosmin_assistant.measurement_rating import MeasurementPropertyRatingResult, RawResultRecord
from cosmin_assistant.models import (
    CosminItemAssessment,
    ModelBase,
    PropertyActivationStatus,
    ReviewerDecisionStatus,
    UncertaintyStatus,
)
from cosmin_assistant.synthesize import SynthesisAggregateResult
from cosmin_assistant.tables.intermediate_models import (
    TableLegendEntry,
    Template5CharacteristicsRow,
    Template5CharacteristicsTable,
    Template6ContentValidityRow,
    Template6ContentValidityTable,
    Template6RowKind,
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
    Template6ContentValidityTable,
    Template7EvidenceTable,
    Template8SummaryTable,
)
_TEMPLATE7_SUBSCALE_FRAGMENT_PATTERN = re.compile(
    r"\b(score|scores|scoring|range|ranges|correlation|correlations|"
    r"spearman|pearson|using|analysis|analyzed)\b",
    flags=re.IGNORECASE,
)
_TEMPLATE7_SUBSCALE_ALLOWED_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 /&+().-]*$")
_TEMPLATE5_EXCLUDED_ROLES: frozenset[InstrumentContextRole] = frozenset(
    {
        InstrumentContextRole.COMPARATOR,
        InstrumentContextRole.COMPARATOR_ONLY,
        InstrumentContextRole.BACKGROUND_ONLY,
    }
)
_TEMPLATE5_PREFERRED_ROLES: frozenset[InstrumentContextRole] = frozenset(
    {
        InstrumentContextRole.TARGET_UNDER_APPRAISAL,
        InstrumentContextRole.CO_PRIMARY_OUTCOME_INSTRUMENT,
        InstrumentContextRole.SECONDARY_OUTCOME_INSTRUMENT,
    }
)
_TEMPLATE5_EXCLUDED_NAME_TOKENS: frozenset[str] = frozenset(
    {
        "ANOVA",
        "ANCOVA",
        "MANOVA",
        "MANCOVA",
        "CFA",
        "EFA",
        "CTT",
        "IRT",
        "WLSMV",
        "PROM",
        "PROMS",
    }
)
_TEMPLATE5_EXCLUDED_NAME_PHRASES: frozenset[str] = frozenset(
    {
        "confirmatory factor analysis",
        "item response theory",
        "classical test theory",
        "weighted least squares mean and variance adjusted",
    }
)
_ARTICLE_AUTHOR_YEAR_TOKEN_PATTERN = re.compile(r"(?P<author>[A-Za-z]+)(?P<year>(?:19|20)\d{2})$")
_ARTICLE_YEAR_TOKEN_PATTERN = re.compile(r"^(?:19|20)\d{2}$")
_ARTICLE_PUBLISHED_YEAR_PATTERN = re.compile(
    r"published(?:\s+online)?[^0-9]{0,40}(?P<year>(?:19|20)\d{2})",
    flags=re.IGNORECASE,
)
_ARTICLE_COPYRIGHT_YEAR_PATTERN = re.compile(
    r"copyright[^0-9]{0,20}(?P<year>(?:19|20)\d{2})",
    flags=re.IGNORECASE,
)
_ARTICLE_YEAR_PATTERN = re.compile(r"\b(?P<year>(?:19|20)\d{2})\b")
_DISPLAY_LABEL_GENERIC_TOKENS: frozenset[str] = frozenset(
    {
        "activity",
        "alpha",
        "amp",
        "article",
        "bank",
        "context",
        "core",
        "e2e",
        "fields",
        "generic",
        "headings",
        "headtohead",
        "holdout",
        "item",
        "latex",
        "longitudinal",
        "markdown",
        "mcid",
        "missing",
        "multiple",
        "nested",
        "nonsci",
        "noisy",
        "patterns",
        "pbom",
        "prom",
        "rasch",
        "repeated",
        "repair",
        "run",
        "sci",
        "statistics",
        "straightforward",
        "subsamples",
        "table",
        "validation",
        "validity",
    }
)


def build_template5_characteristics_table(
    *,
    study_contexts: tuple[StudyContextExtractionResult, ...],
    instrument_contexts: tuple[InstrumentContextExtractionResult, ...],
    measurement_results: tuple[MeasurementPropertyRatingResult, ...] = (),
    article_file_path: str | None = None,
    article_markdown_text: str | None = None,
) -> Template5CharacteristicsTable:
    """Build template 5 equivalent rows for study characteristics."""

    study_by_id = {context.study_id: context for context in study_contexts}
    analyzed_sample_sizes = _template5_analyzed_sample_size_map(measurement_results)
    table_contexts = _template5_table_contexts(instrument_contexts)
    grouped: dict[InstrumentKey, list[InstrumentContextExtractionResult]] = defaultdict(list)
    for context in table_contexts:
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
                    study_display_label=_study_display_label(
                        context.study_id,
                        article_file_path=article_file_path,
                        article_markdown_text=article_markdown_text,
                    ),
                    study_order_within_instrument=index,
                    is_additional_study_row=index > 1,
                    study_design=_study_field_text(study, "study_design"),
                    target_population=_study_field_text(study, "target_population"),
                    language=_study_field_text(study, "language"),
                    country=_study_field_text(study, "country"),
                    enrollment_n=_sample_size_for_role(study, SampleSizeRole.ENROLLMENT),
                    analyzed_n=_template5_analyzed_n(
                        study=study,
                        instrument_context=context,
                        analyzed_sample_sizes=analyzed_sample_sizes,
                    ),
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


def build_template6_content_validity_table(
    *,
    study_contexts: tuple[StudyContextExtractionResult, ...],
    instrument_contexts: tuple[InstrumentContextExtractionResult, ...],
    rob_assessments: tuple[BoxAssessmentBundle, ...],
    article_file_path: str | None = None,
    article_markdown_text: str | None = None,
) -> Template6ContentValidityTable:
    """Build template 6 equivalent rows for PROM development/content validity studies."""

    instrument_key_by_id = _template6_instrument_key_by_id(instrument_contexts)
    target_instrument_ids = {
        context.instrument_id
        for context in instrument_contexts
        if context.instrument_role is InstrumentContextRole.TARGET_UNDER_APPRAISAL
    }
    content_validity_study_ids = _study_ids_with_content_validity_signal(study_contexts)
    box1_pairs = {
        (bundle.box_assessment.study_id, bundle.box_assessment.instrument_id)
        for bundle in rob_assessments
        if bundle.box_assessment.cosmin_box == BOX_1_KEY
    }

    rows: list[Template6ContentValidityRow] = []
    for bundle in sorted(
        rob_assessments,
        key=lambda item: _template6_bundle_sort_key(
            bundle=item,
            instrument_key_by_id=instrument_key_by_id,
        ),
    ):
        box = bundle.box_assessment
        if box.cosmin_box not in (BOX_1_KEY, BOX_2_KEY):
            continue

        if target_instrument_ids and box.instrument_id not in target_instrument_ids:
            continue

        if (
            box.cosmin_box == BOX_2_KEY
            and (box.study_id, box.instrument_id) not in box1_pairs
            and box.study_id not in content_validity_study_ids
        ):
            continue

        instrument_key = instrument_key_by_id.get(
            box.instrument_id,
            (f"instrument:{box.instrument_id}", None, None),
        )
        rows.append(
            Template6ContentValidityRow(
                id=_stable_id(
                    "t6row",
                    "box",
                    instrument_key[0],
                    instrument_key[1] or "",
                    instrument_key[2] or "",
                    box.study_id,
                    box.cosmin_box,
                ),
                row_kind=Template6RowKind.BOX_SUMMARY,
                instrument_name=instrument_key[0],
                instrument_version=instrument_key[1],
                subscale=instrument_key[2],
                study_id=box.study_id,
                study_display_label=_study_display_label(
                    box.study_id,
                    article_file_path=article_file_path,
                    article_markdown_text=article_markdown_text,
                ),
                cosmin_box=box.cosmin_box,
                measurement_property=box.measurement_property,
                box_rating=box.box_rating.value,
                uncertainty_status=box.uncertainty_status.value,
                reviewer_decision_status=box.reviewer_decision_status.value,
            )
        )

        for item in sorted(bundle.item_assessments, key=lambda value: (value.item_code, value.id)):
            rows.append(
                Template6ContentValidityRow(
                    id=_stable_id(
                        "t6row",
                        "item",
                        instrument_key[0],
                        instrument_key[1] or "",
                        instrument_key[2] or "",
                        box.study_id,
                        box.cosmin_box,
                        item.item_code,
                    ),
                    row_kind=Template6RowKind.ITEM,
                    instrument_name=instrument_key[0],
                    instrument_version=instrument_key[1],
                    subscale=instrument_key[2],
                    study_id=box.study_id,
                    study_display_label=_study_display_label(
                        box.study_id,
                        article_file_path=article_file_path,
                        article_markdown_text=article_markdown_text,
                    ),
                    cosmin_box=box.cosmin_box,
                    measurement_property=box.measurement_property,
                    item_code=item.item_code,
                    item_rating=_template6_item_rating_display(item),
                    uncertainty_status=item.uncertainty_status.value,
                    reviewer_decision_status=item.reviewer_decision_status.value,
                )
            )

    return Template6ContentValidityTable(
        id=_stable_id("table", "template_6", len(rows)),
        rows=tuple(rows),
        legends=_template6_legends(),
    )


def build_template7_evidence_table(
    *,
    instrument_contexts: tuple[InstrumentContextExtractionResult, ...],
    rob_assessments: tuple[BoxAssessmentBundle, ...],
    measurement_results: tuple[MeasurementPropertyRatingResult, ...],
    synthesis_results: tuple[SynthesisAggregateResult, ...],
    grade_results: tuple[ModifiedGradeResult, ...],
    measurement_properties_universe: tuple[str, ...] | None = None,
    article_file_path: str | None = None,
    article_markdown_text: str | None = None,
) -> Template7EvidenceTable:
    """Build template 7 equivalent rows with study and summary levels."""

    instrument_key_by_id = _template7_instrument_key_by_id(instrument_contexts)
    grouped_results: dict[tuple[InstrumentKey, str], list[MeasurementPropertyRatingResult]] = (
        defaultdict(list)
    )
    instrument_keys: set[InstrumentKey] = set(
        _template7_instrument_keys_from_contexts(instrument_contexts)
    )

    for result in measurement_results:
        instrument_key = _instrument_key_from_result(result, instrument_key_by_id)
        grouped_results[(instrument_key, result.measurement_property)].append(result)
        instrument_keys.add(instrument_key)

    synthesis_map = _template7_synthesis_map(synthesis_results)
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
            meaningful_study_rows = [
                result for result in study_rows if _is_meaningful_template7_study_result(result)
            ]

            synthesis = synthesis_map.get((instrument_key, measurement_property))
            grade = grade_map.get(synthesis.id) if synthesis is not None else None
            has_meaningful_summary = _has_meaningful_template7_summary(
                synthesis=synthesis,
                grade=grade,
            )

            if not meaningful_study_rows and not has_meaningful_summary:
                continue

            for index, result in enumerate(meaningful_study_rows, start=1):
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
                        study_display_label=_study_display_label(
                            result.study_id,
                            article_file_path=article_file_path,
                            article_markdown_text=article_markdown_text,
                        ),
                        study_order_within_instrument_property=index,
                        is_additional_study_row=index > 1,
                        per_study_rob=rob_map.get(
                            (result.study_id, result.instrument_id, result.measurement_property)
                        ),
                        per_study_result=_raw_result_text(result.raw_results),
                        study_rating=result.computed_rating.value,
                    )
                )

            if has_meaningful_summary:
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


def template6_to_dataframe(table: Template6ContentValidityTable) -> pd.DataFrame:
    """Convert template 6 table rows to a CSV-ready data frame."""

    return _rows_to_dataframe(table.rows)


def _template6_item_rating_display(item: CosminItemAssessment) -> str | None:
    if (
        item.uncertainty_status is UncertaintyStatus.REVIEWER_REQUIRED
        and item.reviewer_decision_status is ReviewerDecisionStatus.PENDING
    ):
        return None
    return item.item_rating.value


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
    frame = pd.DataFrame(payload)
    if "study_display_label" in frame.columns and "study_id" in frame.columns:
        study_values = frame["study_display_label"].where(
            frame["study_display_label"].notna(),
            frame["study_id"],
        )
        if "row_kind" in frame.columns:
            study_values = study_values.where(
                frame["row_kind"] != Template7RowKind.SUMMARY.value,
                "Summary",
            )
        frame.insert(frame.columns.get_loc("study_id"), "study", study_values)
        frame = frame.drop(columns=["study_display_label"])
    return frame


def _study_display_label(
    study_id: str | None,
    *,
    article_file_path: str | None,
    article_markdown_text: str | None,
) -> str | None:
    if study_id is None:
        return None
    citation_label = _article_citation_display_label(
        article_file_path=article_file_path,
        article_markdown_text=article_markdown_text,
    )
    if citation_label is not None:
        return citation_label
    return study_id


def _article_citation_display_label(
    *,
    article_file_path: str | None,
    article_markdown_text: str | None,
) -> str | None:
    author, year = _author_year_from_article_path(article_file_path)
    if year is None:
        year = _publication_year_from_article_text(article_markdown_text)
    if author is None:
        return None
    if year is not None:
        return f"{author} et al., {year}"
    return f"{author} et al."


def _author_year_from_article_path(article_file_path: str | None) -> tuple[str | None, str | None]:
    if article_file_path is None or not article_file_path.strip():
        return None, None

    tokens = [
        token
        for token in re.split(r"[^A-Za-z0-9]+", Path(article_file_path).stem)
        if token.strip()
    ]
    author: str | None = None
    year: str | None = None
    for token in tokens:
        if token.lower() in _DISPLAY_LABEL_GENERIC_TOKENS:
            continue
        author_year_match = _ARTICLE_AUTHOR_YEAR_TOKEN_PATTERN.fullmatch(token)
        if author_year_match is not None:
            return (
                _normalize_author_label(author_year_match.group("author")),
                author_year_match.group("year"),
            )
        if author is None and token.isalpha():
            author = _normalize_author_label(token)
        if year is None and _ARTICLE_YEAR_TOKEN_PATTERN.fullmatch(token):
            year = token
    return author, year


def _publication_year_from_article_text(article_markdown_text: str | None) -> str | None:
    if article_markdown_text is None or not article_markdown_text.strip():
        return None

    header_text = "\n".join(article_markdown_text.splitlines()[:40])
    for pattern in (_ARTICLE_PUBLISHED_YEAR_PATTERN, _ARTICLE_COPYRIGHT_YEAR_PATTERN):
        match = pattern.search(header_text)
        if match is not None:
            return match.group("year")

    fallback_match = _ARTICLE_YEAR_PATTERN.search(header_text)
    if fallback_match is not None:
        return fallback_match.group("year")
    return None


def _normalize_author_label(token: str) -> str:
    return token[0].upper() + token[1:].lower()


def _instrument_keys_from_contexts(
    instrument_contexts: tuple[InstrumentContextExtractionResult, ...],
) -> tuple[InstrumentKey, ...]:
    seen: dict[InstrumentKey, None] = {}
    for context in instrument_contexts:
        seen[_instrument_key_from_context(context)] = None
    return tuple(seen.keys())


def _template5_table_contexts(
    instrument_contexts: tuple[InstrumentContextExtractionResult, ...],
) -> tuple[InstrumentContextExtractionResult, ...]:
    eligible = tuple(
        context for context in instrument_contexts if _template5_is_context_eligible(context)
    )
    preferred = tuple(
        context for context in eligible if context.instrument_role in _TEMPLATE5_PREFERRED_ROLES
    )
    if preferred:
        return preferred
    return eligible


def _template5_is_context_eligible(context: InstrumentContextExtractionResult) -> bool:
    if context.instrument_role in _TEMPLATE5_EXCLUDED_ROLES:
        return False

    instrument_name = _field_text(context.instrument_name)
    return _template5_is_tableworthy_instrument_name(instrument_name)


def _template5_is_tableworthy_instrument_name(instrument_name: str | None) -> bool:
    if instrument_name is None:
        return True

    normalized_name = instrument_name.strip()
    if not normalized_name:
        return False

    normalized_token = re.sub(r"[^A-Za-z0-9]+", "", normalized_name).upper()
    if normalized_token in _TEMPLATE5_EXCLUDED_NAME_TOKENS:
        return False

    normalized_phrase = re.sub(r"\s+", " ", normalized_name).strip().lower()
    return normalized_phrase not in _TEMPLATE5_EXCLUDED_NAME_PHRASES


def _template7_instrument_keys_from_contexts(
    instrument_contexts: tuple[InstrumentContextExtractionResult, ...],
) -> tuple[InstrumentKey, ...]:
    seen: dict[InstrumentKey, None] = {}
    for context in instrument_contexts:
        seen[_template7_instrument_key_from_context(context)] = None
    return tuple(seen.keys())


def _template6_instrument_key_by_id(
    instrument_contexts: tuple[InstrumentContextExtractionResult, ...],
) -> dict[str, InstrumentKey]:
    mapping: dict[str, InstrumentKey] = {}
    for context in sorted(instrument_contexts, key=lambda item: item.id):
        mapping.setdefault(context.instrument_id, _template7_instrument_key_from_context(context))
    return mapping


def _instrument_key_by_id(
    instrument_contexts: tuple[InstrumentContextExtractionResult, ...],
) -> dict[str, InstrumentKey]:
    mapping: dict[str, InstrumentKey] = {}
    for context in sorted(instrument_contexts, key=lambda item: item.id):
        mapping.setdefault(context.instrument_id, _instrument_key_from_context(context))
    return mapping


def _template7_instrument_key_by_id(
    instrument_contexts: tuple[InstrumentContextExtractionResult, ...],
) -> dict[str, InstrumentKey]:
    mapping: dict[str, InstrumentKey] = {}
    for context in sorted(instrument_contexts, key=lambda item: item.id):
        mapping.setdefault(context.instrument_id, _template7_instrument_key_from_context(context))
    return mapping


def _instrument_key_from_context(context: InstrumentContextExtractionResult) -> InstrumentKey:
    instrument_name = _field_text(context.instrument_name) or f"instrument:{context.instrument_id}"
    return (
        instrument_name,
        _field_text(context.instrument_version),
        _field_text(context.subscale),
    )


def _template7_instrument_key_from_context(
    context: InstrumentContextExtractionResult,
) -> InstrumentKey:
    instrument_name = _field_text(context.instrument_name) or f"instrument:{context.instrument_id}"
    return (
        instrument_name,
        _field_text(context.instrument_version),
        _template7_subscale_from_context(context.subscale),
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


def _template7_synthesis_map(
    synthesis_results: tuple[SynthesisAggregateResult, ...],
) -> dict[tuple[InstrumentKey, str], SynthesisAggregateResult]:
    mapping: dict[tuple[InstrumentKey, str], SynthesisAggregateResult] = {}
    for result in sorted(synthesis_results, key=lambda item: item.id):
        key = (
            (
                result.instrument_name,
                result.instrument_version,
                _validated_template7_subscale_text(result.subscale),
            ),
            result.measurement_property,
        )
        mapping.setdefault(key, result)
    return mapping


def _template6_bundle_sort_key(
    *,
    bundle: BoxAssessmentBundle,
    instrument_key_by_id: dict[str, InstrumentKey],
) -> tuple[str, str, str, str, int, str]:
    box = bundle.box_assessment
    instrument_key = instrument_key_by_id.get(
        box.instrument_id,
        (f"instrument:{box.instrument_id}", None, None),
    )
    return (
        instrument_key[0].lower(),
        (instrument_key[1] or "").lower(),
        (instrument_key[2] or "").lower(),
        box.study_id,
        0 if box.cosmin_box == BOX_1_KEY else 1,
        box.id,
    )


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
    if role is SampleSizeRole.ENROLLMENT:
        return _sample_size_for_roles(
            study=study,
            roles=(SampleSizeRole.ENROLLMENT, SampleSizeRole.VALIDATION),
        )
    if role is SampleSizeRole.ANALYZED:
        return _sample_size_for_roles(
            study=study,
            roles=(SampleSizeRole.ANALYZED, SampleSizeRole.VALIDATION),
        )
    return _sample_size_for_roles(study=study, roles=(role,))


def _sample_size_for_roles(
    *,
    study: StudyContextExtractionResult,
    roles: tuple[SampleSizeRole, ...],
) -> int | None:
    observations = sorted(study.sample_size_observations, key=lambda item: item.id)
    for role in roles:
        role_values = [
            observation.sample_size_normalized
            for observation in observations
            if observation.role is role
        ]
        if role_values:
            return max(role_values)
    return None


def _template5_analyzed_n(
    *,
    study: StudyContextExtractionResult | None,
    instrument_context: InstrumentContextExtractionResult,
    analyzed_sample_sizes: dict[tuple[str, str], int],
) -> int | None:
    study_value = _sample_size_for_role(study, SampleSizeRole.ANALYZED)
    if study_value is not None:
        return study_value
    return analyzed_sample_sizes.get((instrument_context.study_id, instrument_context.instrument_id))


def _template5_analyzed_sample_size_map(
    measurement_results: tuple[MeasurementPropertyRatingResult, ...],
) -> dict[tuple[str, str], int]:
    grouped: dict[tuple[str, str], set[int]] = defaultdict(set)
    for result in measurement_results:
        sample_size_raw = result.inputs_used.get("sample_size_selected")
        if not isinstance(sample_size_raw, int) or sample_size_raw < 0:
            continue
        grouped[(result.study_id, result.instrument_id)].add(sample_size_raw)

    resolved: dict[tuple[str, str], int] = {}
    for key, sample_sizes in grouped.items():
        if len(sample_sizes) == 1:
            resolved[key] = next(iter(sample_sizes))
    return resolved


def _raw_result_text(raw_results: tuple[RawResultRecord, ...]) -> str | None:
    if not raw_results:
        return None
    parts: list[str] = []
    for record in raw_results:
        stat = record.statistic_type.value
        subgroup = f"[{record.subgroup_label}]" if record.subgroup_label else ""
        parts.append(f"{stat}{subgroup}={record.value_raw}")
    return "; ".join(parts)


def _is_meaningful_template7_study_result(result: MeasurementPropertyRatingResult) -> bool:
    if result.activation_status is not PropertyActivationStatus.DIRECT_CURRENT_STUDY_EVIDENCE:
        return False
    return bool(
        result.raw_results
        or result.threshold_comparisons
        or result.prerequisite_decisions
        or result.evidence_span_ids
    )


def _has_meaningful_template7_summary(
    *,
    synthesis: SynthesisAggregateResult | None,
    grade: ModifiedGradeResult | None,
) -> bool:
    if synthesis is None:
        return False
    return any(
        (
            bool(synthesis.summary_explanation),
            synthesis.summary_rating is not None,
            grade is not None and grade.final_certainty is not None,
            synthesis.total_sample_size is not None,
        )
    )


def _template7_subscale_from_context(field: ContextFieldExtraction) -> str | None:
    if field.status is not FieldDetectionStatus.DETECTED:
        return None
    if len(field.candidates) != 1:
        return None
    return _validated_template7_subscale_text(_candidate_value_text(field.candidates[0]))


def _validated_template7_subscale_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > 48:
        return None
    if any(token in normalized for token in ("|", ",", ";", ":", "=")):
        return None
    if _TEMPLATE7_SUBSCALE_FRAGMENT_PATTERN.search(normalized):
        return None
    if _TEMPLATE7_SUBSCALE_ALLOWED_PATTERN.match(normalized) is None:
        return None
    return normalized


def _study_ids_with_content_validity_signal(
    study_contexts: tuple[StudyContextExtractionResult, ...],
) -> set[str]:
    matching: set[str] = set()
    for study in study_contexts:
        if _field_mentions_property(
            field=study.measurement_properties_mentioned,
            property_name="content_validity",
        ):
            matching.add(study.study_id)
    return matching


def _field_mentions_property(*, field: ContextFieldExtraction, property_name: str) -> bool:
    expected = _normalized_property_token(property_name)
    for candidate in field.candidates:
        for token in _candidate_property_tokens(candidate):
            if token == expected:
                return True
    return False


def _candidate_property_tokens(candidate: ContextValueCandidate) -> tuple[str, ...]:
    value = candidate.normalized_value
    if isinstance(value, tuple):
        values = [item for item in value if isinstance(item, str)]
    elif isinstance(value, str):
        values = [value]
    else:
        values = []

    if not values and candidate.raw_text:
        values = [candidate.raw_text]

    deduped: list[str] = []
    for item in values:
        normalized = _normalized_property_token(item)
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return tuple(deduped)


def _normalized_property_token(value: str) -> str:
    compact = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return compact


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


def _template6_legends() -> tuple[TableLegendEntry, ...]:
    return (
        TableLegendEntry(
            key="box_summary",
            description="Box-level reviewer-required/manual assessment summary row.",
        ),
        TableLegendEntry(
            key="item",
            description="Item-level row; pending/manual state appears in status columns.",
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
