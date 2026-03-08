"""Deterministic first-pass extraction of study and instrument context fields."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from cosmin_assistant.extract.context_models import (
    ArticleContextExtractionResult,
    ContextFieldExtraction,
    ContextValueCandidate,
    FieldDetectionStatus,
    InstrumentContextExtractionResult,
    StudyContextExtractionResult,
    SubsampleExtraction,
)
from cosmin_assistant.extract.markdown_parser import parse_markdown_file
from cosmin_assistant.extract.spans import ParsedMarkdownDocument, SentenceRecord
from cosmin_assistant.models.base import StableId

_NOT_REPORTED_RE = re.compile(
    r"\b(not reported|not stated|not available|not described|unknown)\b",
    flags=re.IGNORECASE,
)
_SUBSAMPLE_RE = re.compile(
    r"\bsubsample\s+([A-Za-z0-9][A-Za-z0-9 _-]*)\s*\(\s*[nN]\s*=\s*(\d+)\s*\)",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class _CandidateDraft:
    raw_text: str
    normalized_value: str | int | tuple[str, ...] | None
    evidence_span_id: StableId


def extract_context_from_markdown_file(file_path: str | Path) -> ArticleContextExtractionResult:
    """Extract first-pass study/instrument context fields from a markdown file."""

    parsed = parse_markdown_file(file_path)
    return extract_context_from_parsed_document(parsed)


def extract_context_from_parsed_document(
    parsed: ParsedMarkdownDocument,
) -> ArticleContextExtractionResult:
    """Extract first-pass context using parsed span-level markdown representation."""

    sentences = parsed.sentences
    study_id = _stable_id("study", parsed.id, "default")

    instrument_name = _extract_instrument_name(parsed.file_path, sentences)
    instrument_version = _extract_instrument_version(parsed.file_path, sentences)
    subscale = _extract_subscale(parsed.file_path, sentences)
    construct = _extract_construct(parsed.file_path, sentences)
    target_population = _extract_target_population(parsed.file_path, sentences)

    language = _extract_language(parsed.file_path, sentences)
    country = _extract_country(parsed.file_path, sentences)
    study_design = _extract_study_design(parsed.file_path, sentences)
    sample_sizes = _extract_sample_sizes(parsed.file_path, sentences)
    measurement_properties = _extract_measurement_properties(parsed.file_path, sentences)
    subsamples = _extract_subsamples(parsed.file_path, sentences)

    if instrument_name.status is FieldDetectionStatus.DETECTED:
        instrument_discriminator = str(instrument_name.candidates[0].normalized_value)
    else:
        instrument_discriminator = "unknown"

    instrument_id = _stable_id("inst", parsed.id, instrument_discriminator)

    study_context = StudyContextExtractionResult(
        id=_stable_id("studyctx", parsed.id, study_id),
        article_id=parsed.id,
        study_id=study_id,
        study_design=study_design,
        sample_sizes=sample_sizes,
        construct_field=construct,
        target_population=target_population,
        language=language,
        country=country,
        measurement_properties_mentioned=measurement_properties,
        subsamples=subsamples,
    )

    instrument_context = InstrumentContextExtractionResult(
        id=_stable_id("instctx", parsed.id, instrument_id),
        article_id=parsed.id,
        study_id=study_id,
        instrument_id=instrument_id,
        instrument_name=instrument_name,
        instrument_version=instrument_version,
        subscale=subscale,
        construct_field=construct,
        target_population=target_population,
    )

    return ArticleContextExtractionResult(
        id=_stable_id("articlectx", parsed.id, parsed.file_path),
        article_id=parsed.id,
        file_path=parsed.file_path,
        study_contexts=(study_context,),
        instrument_contexts=(instrument_context,),
    )


def _extract_instrument_name(
    file_path: str,
    sentences: tuple[SentenceRecord, ...],
) -> ContextFieldExtraction:
    drafts: list[_CandidateDraft] = []
    patterns = (
        re.compile(
            r"(?:instrument(?: name)?|questionnaire|tool)\s*[:=-]\s*"
            r"([A-Za-z][A-Za-z0-9\-_/() ]+)",
            flags=re.IGNORECASE,
        ),
        re.compile(r"\busing (?:the )?([A-Z][A-Za-z0-9\-_/]*(?: [A-Za-z0-9\-_/]+){0,4})"),
    )

    for sentence in sentences:
        text = sentence.provenance.raw_text
        for pattern in patterns:
            match = pattern.search(text)
            if not match:
                continue
            value = _normalize_text_value(match.group(1))
            if _NOT_REPORTED_RE.search(value):
                continue
            if value:
                drafts.append(
                    _CandidateDraft(
                        raw_text=match.group(0),
                        normalized_value=value,
                        evidence_span_id=sentence.id,
                    )
                )

    return _build_field_extraction(
        file_path,
        "instrument_name",
        drafts,
        _collect_not_reported_candidates(
            field_aliases=("instrument", "questionnaire", "scale", "measure", "tool"),
            sentences=sentences,
        ),
    )


def _extract_instrument_version(
    file_path: str,
    sentences: tuple[SentenceRecord, ...],
) -> ContextFieldExtraction:
    drafts: list[_CandidateDraft] = []
    pattern = re.compile(
        r"(?:instrument\s+version|version|\bv)\s*[:=-]?\s*(v?\d+(?:\.\d+)*)",
        flags=re.IGNORECASE,
    )

    for sentence in sentences:
        text = sentence.provenance.raw_text
        match = pattern.search(text)
        if not match:
            continue
        normalized = _normalize_version(match.group(1))
        if _NOT_REPORTED_RE.search(normalized):
            continue
        drafts.append(
            _CandidateDraft(
                raw_text=match.group(0),
                normalized_value=normalized,
                evidence_span_id=sentence.id,
            )
        )

    return _build_field_extraction(
        file_path,
        "instrument_version",
        drafts,
        _collect_not_reported_candidates(field_aliases=("version",), sentences=sentences),
    )


def _extract_subscale(
    file_path: str,
    sentences: tuple[SentenceRecord, ...],
) -> ContextFieldExtraction:
    drafts: list[_CandidateDraft] = []
    pattern = re.compile(
        r"subscale\s*[:=-]?\s*([A-Za-z][A-Za-z0-9\-_/() ]+)",
        flags=re.IGNORECASE,
    )

    for sentence in sentences:
        text = sentence.provenance.raw_text
        match = pattern.search(text)
        if not match:
            continue
        value = _normalize_text_value(match.group(1))
        if _NOT_REPORTED_RE.search(value):
            continue
        if value:
            drafts.append(
                _CandidateDraft(
                    raw_text=match.group(0),
                    normalized_value=value,
                    evidence_span_id=sentence.id,
                )
            )

    return _build_field_extraction(
        file_path,
        "subscale",
        drafts,
        _collect_not_reported_candidates(field_aliases=("subscale",), sentences=sentences),
    )


def _extract_construct(
    file_path: str,
    sentences: tuple[SentenceRecord, ...],
) -> ContextFieldExtraction:
    drafts: list[_CandidateDraft] = []
    pattern = re.compile(
        r"construct\s*[:=-]?\s*([A-Za-z][A-Za-z0-9\-_/(), ]+)",
        flags=re.IGNORECASE,
    )

    for sentence in sentences:
        text = sentence.provenance.raw_text
        match = pattern.search(text)
        if not match:
            continue
        value = _normalize_text_value(match.group(1))
        if _NOT_REPORTED_RE.search(value):
            continue
        if value:
            drafts.append(
                _CandidateDraft(
                    raw_text=match.group(0),
                    normalized_value=value,
                    evidence_span_id=sentence.id,
                )
            )

    return _build_field_extraction(
        file_path,
        "construct",
        drafts,
        _collect_not_reported_candidates(field_aliases=("construct",), sentences=sentences),
    )


def _extract_target_population(
    file_path: str,
    sentences: tuple[SentenceRecord, ...],
) -> ContextFieldExtraction:
    drafts: list[_CandidateDraft] = []
    pattern = re.compile(
        r"target\s+population\s*[:=-]?\s*([A-Za-z][A-Za-z0-9\-_/(), ]+)",
        flags=re.IGNORECASE,
    )

    for sentence in sentences:
        text = sentence.provenance.raw_text
        match = pattern.search(text)
        if not match:
            continue
        value = _normalize_text_value(match.group(1))
        if _NOT_REPORTED_RE.search(value):
            continue
        if value:
            drafts.append(
                _CandidateDraft(
                    raw_text=match.group(0),
                    normalized_value=value,
                    evidence_span_id=sentence.id,
                )
            )

    return _build_field_extraction(
        file_path,
        "target_population",
        drafts,
        _collect_not_reported_candidates(
            field_aliases=("target population", "population"),
            sentences=sentences,
        ),
    )


def _extract_language(
    file_path: str,
    sentences: tuple[SentenceRecord, ...],
) -> ContextFieldExtraction:
    drafts: list[_CandidateDraft] = []
    pattern = re.compile(
        r"language\s*[:=-]?\s*([A-Za-z][A-Za-z .-]+)",
        flags=re.IGNORECASE,
    )

    for sentence in sentences:
        text = sentence.provenance.raw_text
        match = pattern.search(text)
        if not match:
            continue
        value = _normalize_language(match.group(1))
        if _NOT_REPORTED_RE.search(value):
            continue
        drafts.append(
            _CandidateDraft(
                raw_text=match.group(0),
                normalized_value=value,
                evidence_span_id=sentence.id,
            )
        )

    return _build_field_extraction(
        file_path,
        "language",
        drafts,
        _collect_not_reported_candidates(field_aliases=("language",), sentences=sentences),
    )


def _extract_country(
    file_path: str,
    sentences: tuple[SentenceRecord, ...],
) -> ContextFieldExtraction:
    drafts: list[_CandidateDraft] = []
    pattern = re.compile(
        r"country\s*[:=-]?\s*([A-Za-z][A-Za-z .'-]+)",
        flags=re.IGNORECASE,
    )

    for sentence in sentences:
        text = sentence.provenance.raw_text
        match = pattern.search(text)
        if not match:
            continue
        value = _normalize_country(match.group(1))
        if _NOT_REPORTED_RE.search(value):
            continue
        drafts.append(
            _CandidateDraft(
                raw_text=match.group(0),
                normalized_value=value,
                evidence_span_id=sentence.id,
            )
        )

    return _build_field_extraction(
        file_path,
        "country",
        drafts,
        _collect_not_reported_candidates(field_aliases=("country",), sentences=sentences),
    )


def _extract_study_design(
    file_path: str,
    sentences: tuple[SentenceRecord, ...],
) -> ContextFieldExtraction:
    drafts: list[_CandidateDraft] = []

    design_map: tuple[tuple[str, str], ...] = (
        ("cross-sectional validation study", "cross_sectional_validation_study"),
        ("longitudinal cohort", "longitudinal_cohort"),
        ("randomized controlled trial", "randomized_controlled_trial"),
        ("cross-sectional", "cross_sectional"),
        ("cohort", "cohort"),
        ("case-control", "case_control"),
        ("longitudinal", "longitudinal"),
        ("validation study", "validation_study"),
    )

    for sentence in sentences:
        text_lower = sentence.provenance.raw_text.lower()
        for needle, normalized in design_map:
            if needle in text_lower:
                drafts.append(
                    _CandidateDraft(
                        raw_text=sentence.provenance.raw_text,
                        normalized_value=normalized,
                        evidence_span_id=sentence.id,
                    )
                )
                break

    return _build_field_extraction(
        file_path,
        "study_design",
        drafts,
        _collect_not_reported_candidates(
            field_aliases=("study design", "design"),
            sentences=sentences,
        ),
    )


def _extract_sample_sizes(
    file_path: str,
    sentences: tuple[SentenceRecord, ...],
) -> ContextFieldExtraction:
    drafts: list[_CandidateDraft] = []
    n_pattern = re.compile(r"\b[nN]\s*=\s*(\d+)\b")

    for sentence in sentences:
        text = sentence.provenance.raw_text
        if "subsample" in text.lower():
            continue
        for match in n_pattern.finditer(text):
            drafts.append(
                _CandidateDraft(
                    raw_text=match.group(0),
                    normalized_value=int(match.group(1)),
                    evidence_span_id=sentence.id,
                )
            )

    return _build_field_extraction(
        file_path,
        "sample_sizes",
        drafts,
        _collect_not_reported_candidates(
            field_aliases=("sample size", "n =", "participants"),
            sentences=sentences,
        ),
    )


def _extract_measurement_properties(
    file_path: str,
    sentences: tuple[SentenceRecord, ...],
) -> ContextFieldExtraction:
    property_needles: tuple[tuple[str, str], ...] = (
        ("content validity", "content_validity"),
        ("structural validity", "structural_validity"),
        ("internal consistency", "internal_consistency"),
        (
            "cross-cultural validity",
            "cross_cultural_validity_measurement_invariance",
        ),
        ("measurement invariance", "cross_cultural_validity_measurement_invariance"),
        ("reliability", "reliability"),
        ("measurement error", "measurement_error"),
        ("criterion validity", "criterion_validity"),
        ("construct validity", "hypotheses_testing_for_construct_validity"),
        (
            "hypotheses testing",
            "hypotheses_testing_for_construct_validity",
        ),
        ("responsiveness", "responsiveness"),
    )

    matched_properties: set[str] = set()
    evidence_ids: list[StableId] = []
    raw_segments: list[str] = []

    for sentence in sentences:
        text_lower = sentence.provenance.raw_text.lower()
        found_here: list[str] = []
        for needle, normalized in property_needles:
            if needle in text_lower:
                found_here.append(normalized)

        if found_here:
            matched_properties.update(found_here)
            evidence_ids.append(sentence.id)
            raw_segments.append(sentence.provenance.raw_text)

    drafts: list[_CandidateDraft] = []
    if matched_properties:
        normalized_tuple = tuple(sorted(matched_properties))
        drafts.append(
            _CandidateDraft(
                raw_text=" || ".join(raw_segments),
                normalized_value=normalized_tuple,
                evidence_span_id=evidence_ids[0],
            )
        )

    return _build_field_extraction(
        file_path,
        "measurement_properties_mentioned",
        drafts,
        _collect_not_reported_candidates(
            field_aliases=("measurement propert", "property"),
            sentences=sentences,
        ),
    )


def _extract_subsamples(
    file_path: str,
    sentences: tuple[SentenceRecord, ...],
) -> tuple[SubsampleExtraction, ...]:
    records: list[SubsampleExtraction] = []

    for sentence in sentences:
        text = sentence.provenance.raw_text
        for match in _SUBSAMPLE_RE.finditer(text):
            label_raw = match.group(1).strip()
            label_normalized = re.sub(r"\s+", " ", label_raw).strip().lower()
            n_raw = match.group(2)
            records.append(
                SubsampleExtraction(
                    id=_stable_id(
                        "subsample",
                        file_path,
                        sentence.id,
                        label_normalized,
                        n_raw,
                    ),
                    label_raw=label_raw,
                    label_normalized=label_normalized,
                    sample_size_raw=n_raw,
                    sample_size_normalized=int(n_raw),
                    evidence_span_ids=(sentence.id,),
                )
            )

    return tuple(records)


def _collect_not_reported_candidates(
    *,
    field_aliases: tuple[str, ...],
    sentences: tuple[SentenceRecord, ...],
) -> list[_CandidateDraft]:
    drafts: list[_CandidateDraft] = []

    for sentence in sentences:
        text = sentence.provenance.raw_text
        text_lower = text.lower()
        if not any(alias in text_lower for alias in field_aliases):
            continue
        if not _NOT_REPORTED_RE.search(text):
            continue
        drafts.append(
            _CandidateDraft(
                raw_text=text,
                normalized_value=None,
                evidence_span_id=sentence.id,
            )
        )

    return drafts


def _build_field_extraction(
    file_path: str,
    field_name: str,
    detected_candidates: list[_CandidateDraft],
    not_reported_candidates: list[_CandidateDraft],
) -> ContextFieldExtraction:
    grouped: dict[str | int | tuple[str, ...] | None, list[_CandidateDraft]] = defaultdict(list)

    for candidate in detected_candidates:
        grouped[candidate.normalized_value].append(candidate)

    grouped.pop(None, None)

    if grouped:
        if len(grouped) == 1:
            normalized_value, grouped_candidates = next(iter(grouped.items()))
            collapsed_candidate = _collapse_group(
                file_path,
                field_name,
                normalized_value,
                grouped_candidates,
            )
            return ContextFieldExtraction(
                id=_stable_id("field", file_path, field_name, FieldDetectionStatus.DETECTED.value),
                field_name=field_name,
                status=FieldDetectionStatus.DETECTED,
                candidates=(collapsed_candidate,),
            )

        candidates: list[ContextValueCandidate] = []
        for normalized_value, grouped_candidates in sorted(
            grouped.items(), key=lambda item: str(item[0])
        ):
            candidates.append(
                _collapse_group(file_path, field_name, normalized_value, grouped_candidates)
            )
        return ContextFieldExtraction(
            id=_stable_id("field", file_path, field_name, FieldDetectionStatus.AMBIGUOUS.value),
            field_name=field_name,
            status=FieldDetectionStatus.AMBIGUOUS,
            candidates=tuple(candidates),
        )

    if not_reported_candidates:
        not_reported_items = tuple(
            ContextValueCandidate(
                id=_stable_id("cand", file_path, field_name, draft.evidence_span_id),
                raw_text=draft.raw_text,
                normalized_value=None,
                evidence_span_ids=(draft.evidence_span_id,),
            )
            for draft in not_reported_candidates
        )
        return ContextFieldExtraction(
            id=_stable_id(
                "field",
                file_path,
                field_name,
                FieldDetectionStatus.NOT_REPORTED.value,
            ),
            field_name=field_name,
            status=FieldDetectionStatus.NOT_REPORTED,
            candidates=not_reported_items,
        )

    return ContextFieldExtraction(
        id=_stable_id(
            "field",
            file_path,
            field_name,
            FieldDetectionStatus.NOT_DETECTED.value,
        ),
        field_name=field_name,
        status=FieldDetectionStatus.NOT_DETECTED,
        candidates=(),
    )


def _collapse_group(
    file_path: str,
    field_name: str,
    normalized_value: str | int | tuple[str, ...] | None,
    grouped_candidates: list[_CandidateDraft],
) -> ContextValueCandidate:
    evidence_ids = tuple(
        dict.fromkeys(candidate.evidence_span_id for candidate in grouped_candidates)
    )
    raw_text = " || ".join(dict.fromkeys(candidate.raw_text for candidate in grouped_candidates))
    return ContextValueCandidate(
        id=_stable_id("cand", file_path, field_name, str(normalized_value), *evidence_ids),
        raw_text=raw_text,
        normalized_value=normalized_value,
        evidence_span_ids=evidence_ids,
    )


def _normalize_text_value(raw_value: str) -> str:
    value = re.sub(r"\s+", " ", raw_value).strip(" .;:,\t")
    return value


def _normalize_version(raw_value: str) -> str:
    value = raw_value.strip().lower().removeprefix("version ")
    return value.removeprefix("v")


def _normalize_language(raw_value: str) -> str:
    value = _normalize_text_value(raw_value)
    return value.title()


def _normalize_country(raw_value: str) -> str:
    value = _normalize_text_value(raw_value)
    value_lower = value.lower()
    aliases = {
        "usa": "United States",
        "u.s.a": "United States",
        "u.s.a.": "United States",
        "us": "United States",
        "u.s.": "United States",
        "uk": "United Kingdom",
        "u.k.": "United Kingdom",
    }
    return aliases.get(value_lower, value.title())


def _stable_id(prefix: str, *parts: object) -> StableId:
    serialized = "|".join(str(part) for part in parts)
    digest = hashlib.sha1(f"{prefix}|{serialized}".encode()).hexdigest()[:16]
    return f"{prefix}.{digest}"
