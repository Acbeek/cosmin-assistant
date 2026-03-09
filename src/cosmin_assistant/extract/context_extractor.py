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
    SampleSizeObservation,
    SampleSizeRole,
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
_INSTRUMENT_CONTEXT_RE = re.compile(
    r"\b("
    r"questionnaire|patient-reported|outcome measure|domain score|scores?|"
    r"completed|baseline|follow-up"
    r")\b",
    flags=re.IGNORECASE,
)
_NON_INSTRUMENT_CONTEXT_RE = re.compile(
    r"\b("
    r"device|implant|system|calculator|hospital|medical center|"
    r"software|protocol|fda|registry"
    r")\b",
    flags=re.IGNORECASE,
)
_INSTRUMENT_LABEL_RE = re.compile(
    r"(?:instrument(?: name)?|questionnaire|measure|tool)\s*[:=-]\s*"
    r"([A-Za-z][A-Za-z0-9\-_/() ]{1,120})",
    flags=re.IGNORECASE,
)
_INSTRUMENT_ACRONYM_RE = re.compile(r"\b([A-Z][A-Z0-9]+(?:-[A-Z0-9]+)+|[A-Z]{4,10})\b")
_QTFA_FULL_RE = re.compile(
    r"questionnaire\s+for\s+persons\s+with\s+a\s+transfemoral\s+amputation",
    flags=re.IGNORECASE,
)
_PROMIS_FULL_RE = re.compile(
    r"patient-?reported\s+outcomes\s+measurement\s+information\s+system",
    flags=re.IGNORECASE,
)
_QTFA_ABBR_RE = re.compile(r"\bq\s*-?\s*tfa\b", flags=re.IGNORECASE)
_PROMIS_ABBR_RE = re.compile(r"\bpromis\b", flags=re.IGNORECASE)
_CITATION_RE = re.compile(r"\[[0-9,\s]+\]|\bet\s+al\.\b", flags=re.IGNORECASE)
_INTERVAL_RE = re.compile(r"\b(\d+)\s*(month|months|week|weeks|year|years)\b", flags=re.IGNORECASE)
_ENROLLMENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?:recruited|enrolled|included)\s*(\d+)\s*(?:participants?|patients?|subjects?)\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\bstudy\s+of\s+(\d+)\s*(?:participants?|patients?|subjects?)\b",
        flags=re.IGNORECASE,
    ),
)
_ANALYZED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\bleaving[^.]{0,160}\(\s*(\d+)\s+of\s+\d+\s*\)\s+for\s+analysis\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\bfinal\s+population[^.]{0,120}\b(?:consisted\s+of|was)\s+"
        r"(\d+)\s+(?:participants?|patients?|subjects?)\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\b(\d+)\s+(?:participants?|patients?|subjects?)\b[^.]{0,120}\breached\b[^.]{0,60}\bfollow-up\b",
        flags=re.IGNORECASE,
    ),
)
_LIMB_LEVEL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\btotal\s+of\s+(\d+)\s+limbs\b", flags=re.IGNORECASE),
    re.compile(
        r"\b(\d+)\s+limbs\b[^.]{0,80}\bunderwent\s+osseointegration\b",
        flags=re.IGNORECASE,
    ),
)
_SAMPLE_SIZE_N_RE = re.compile(r"\b[nN]\s*=\s*(\d+)\b")


@dataclass(frozen=True)
class _CandidateDraft:
    raw_text: str
    normalized_value: str | int | tuple[str, ...] | None
    evidence_span_id: StableId


@dataclass(frozen=True)
class _InstrumentMentionDraft:
    normalized_name: str
    raw_text: str
    evidence_span_id: StableId
    strength: int


@dataclass(frozen=True)
class _SampleSizeDraft:
    role: SampleSizeRole
    raw_text: str
    normalized_value: int
    unit: str | None
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

    instrument_name_fields = _extract_preferred_instrument_name_fields(parsed.file_path, sentences)
    if not instrument_name_fields:
        instrument_name_fields = (_extract_instrument_name(parsed.file_path, sentences),)

    instrument_version = _extract_instrument_version(parsed.file_path, sentences)
    subscale = _extract_subscale(parsed.file_path, sentences)
    construct = _extract_construct(parsed.file_path, sentences)
    target_population = _extract_target_population(parsed.file_path, sentences)

    language = _extract_language(parsed.file_path, sentences)
    country = _extract_country(parsed.file_path, sentences)
    study_design = _extract_study_design(parsed.file_path, sentences)
    sample_sizes = _extract_sample_sizes(parsed.file_path, sentences)
    sample_size_observations = _extract_sample_size_observations(
        parsed.file_path,
        sentences,
        sample_sizes,
    )
    follow_up_schedule = _extract_follow_up_schedule(parsed.file_path, sentences)
    (
        measurement_properties,
        measurement_properties_background,
        measurement_properties_interpretability,
    ) = _extract_measurement_property_partitions(parsed.file_path, sentences)
    subsamples = _extract_subsamples(parsed.file_path, sentences)

    study_context = StudyContextExtractionResult(
        id=_stable_id("studyctx", parsed.id, study_id),
        article_id=parsed.id,
        study_id=study_id,
        study_design=study_design,
        sample_sizes=sample_sizes,
        sample_size_observations=sample_size_observations,
        follow_up_schedule=follow_up_schedule,
        construct_field=construct,
        target_population=target_population,
        language=language,
        country=country,
        measurement_properties_mentioned=measurement_properties,
        measurement_properties_background=measurement_properties_background,
        measurement_properties_interpretability=measurement_properties_interpretability,
        subsamples=subsamples,
    )

    instrument_contexts = _build_instrument_contexts(
        article_id=parsed.id,
        study_id=study_id,
        file_path=parsed.file_path,
        instrument_name_fields=instrument_name_fields,
        instrument_version=instrument_version,
        subscale=subscale,
        construct=construct,
        target_population=target_population,
    )

    return ArticleContextExtractionResult(
        id=_stable_id("articlectx", parsed.id, parsed.file_path),
        article_id=parsed.id,
        file_path=parsed.file_path,
        study_contexts=(study_context,),
        instrument_contexts=instrument_contexts,
    )


def _build_instrument_contexts(
    *,
    article_id: StableId,
    study_id: StableId,
    file_path: str,
    instrument_name_fields: tuple[ContextFieldExtraction, ...],
    instrument_version: ContextFieldExtraction,
    subscale: ContextFieldExtraction,
    construct: ContextFieldExtraction,
    target_population: ContextFieldExtraction,
) -> tuple[InstrumentContextExtractionResult, ...]:
    contexts: list[InstrumentContextExtractionResult] = []

    sorted_fields = sorted(
        instrument_name_fields,
        key=lambda field: (
            field.status.value,
            _first_candidate_normalized(field) or "",
            field.id,
        ),
    )

    for index, instrument_name in enumerate(sorted_fields):
        discriminator = _first_candidate_normalized(instrument_name) or f"unknown-{index}"
        instrument_id = _stable_id("inst", article_id, discriminator)
        contexts.append(
            InstrumentContextExtractionResult(
                id=_stable_id("instctx", file_path, article_id, study_id, instrument_id),
                article_id=article_id,
                study_id=study_id,
                instrument_id=instrument_id,
                instrument_name=instrument_name,
                instrument_version=instrument_version,
                subscale=subscale,
                construct_field=construct,
                target_population=target_population,
            )
        )

    return tuple(contexts)


def _extract_preferred_instrument_name_fields(
    file_path: str,
    sentences: tuple[SentenceRecord, ...],
) -> tuple[ContextFieldExtraction, ...]:
    mentions = _collect_instrument_mentions(sentences)
    if not mentions:
        return ()

    grouped: dict[str, list[_InstrumentMentionDraft]] = defaultdict(list)
    for mention in mentions:
        grouped[mention.normalized_name].append(mention)

    selected_fields: list[ContextFieldExtraction] = []
    for normalized_name, records in sorted(grouped.items(), key=lambda item: item[0]):
        evidence_span_ids = tuple(dict.fromkeys(record.evidence_span_id for record in records))
        mention_count = len(evidence_span_ids)
        strongest = max(record.strength for record in records)

        # Keep only high-confidence instrument entities as standalone contexts.
        if mention_count < 2 and strongest < 4:
            continue

        raw_text = " || ".join(dict.fromkeys(record.raw_text for record in records))
        candidate = ContextValueCandidate(
            id=_stable_id(
                "cand", file_path, "instrument_name", normalized_name, *evidence_span_ids
            ),
            raw_text=raw_text,
            normalized_value=normalized_name,
            evidence_span_ids=evidence_span_ids,
        )
        selected_fields.append(
            ContextFieldExtraction(
                id=_stable_id(
                    "field",
                    file_path,
                    "instrument_name",
                    normalized_name,
                    FieldDetectionStatus.DETECTED.value,
                ),
                field_name="instrument_name",
                status=FieldDetectionStatus.DETECTED,
                candidates=(candidate,),
            )
        )

    return tuple(selected_fields)


def _collect_instrument_mentions(
    sentences: tuple[SentenceRecord, ...],
) -> tuple[_InstrumentMentionDraft, ...]:
    by_key: dict[tuple[str, StableId], _InstrumentMentionDraft] = {}

    for sentence in sentences:
        if _is_reference_sentence(sentence):
            continue

        text = sentence.provenance.raw_text
        text_lower = text.lower()
        context_bonus = 2 if _INSTRUMENT_CONTEXT_RE.search(text) else 0
        context_penalty = -3 if _NON_INSTRUMENT_CONTEXT_RE.search(text) else 0

        if _QTFA_FULL_RE.search(text):
            _add_instrument_mention(
                by_key=by_key,
                sentence=sentence,
                raw_value="Q-TFA",
                normalized_name="Q-TFA",
                base_strength=4,
                context_bonus=context_bonus,
                context_penalty=context_penalty,
            )
        if _PROMIS_FULL_RE.search(text):
            _add_instrument_mention(
                by_key=by_key,
                sentence=sentence,
                raw_value="PROMIS",
                normalized_name="PROMIS",
                base_strength=4,
                context_bonus=context_bonus,
                context_penalty=context_penalty,
            )

        for match in _QTFA_ABBR_RE.finditer(text):
            _add_instrument_mention(
                by_key=by_key,
                sentence=sentence,
                raw_value=match.group(0),
                normalized_name="Q-TFA",
                base_strength=3,
                context_bonus=context_bonus,
                context_penalty=context_penalty,
            )
        for match in _PROMIS_ABBR_RE.finditer(text):
            _add_instrument_mention(
                by_key=by_key,
                sentence=sentence,
                raw_value=match.group(0),
                normalized_name="PROMIS",
                base_strength=3,
                context_bonus=context_bonus,
                context_penalty=context_penalty,
            )

        for match in _INSTRUMENT_LABEL_RE.finditer(text):
            value = _normalize_instrument_name_candidate(match.group(1))
            if not value:
                continue
            if _is_false_instrument_candidate(value, sentence):
                continue
            key = (value, sentence.id)
            draft = _InstrumentMentionDraft(
                normalized_name=value,
                raw_text=match.group(0),
                evidence_span_id=sentence.id,
                strength=max(2 + context_bonus + context_penalty, 1),
            )
            current = by_key.get(key)
            if current is None or draft.strength > current.strength:
                by_key[key] = draft

        if _INSTRUMENT_CONTEXT_RE.search(text):
            for match in _INSTRUMENT_ACRONYM_RE.finditer(text):
                token = match.group(1)
                value = _normalize_instrument_name_candidate(token)
                if not value:
                    continue
                if _is_false_instrument_candidate(value, sentence):
                    continue
                if not ("-" in value or value.startswith("PROM")):
                    continue
                key = (value, sentence.id)
                draft = _InstrumentMentionDraft(
                    normalized_name=value,
                    raw_text=token,
                    evidence_span_id=sentence.id,
                    strength=max(1 + context_bonus + context_penalty, 1),
                )
                current = by_key.get(key)
                if current is None or draft.strength > current.strength:
                    by_key[key] = draft

        # Keep explicit abbreviated mentions inside long-form clauses.
        if "questionnaire" in text_lower and "(" in text and ")" in text:
            for token in re.findall(r"\(([A-Za-z0-9\- ]{2,20})\)", text):
                value = _normalize_instrument_name_candidate(token)
                if not value:
                    continue
                if _is_false_instrument_candidate(value, sentence):
                    continue
                key = (value, sentence.id)
                draft = _InstrumentMentionDraft(
                    normalized_name=value,
                    raw_text=token,
                    evidence_span_id=sentence.id,
                    strength=max(2 + context_bonus + context_penalty, 1),
                )
                current = by_key.get(key)
                if current is None or draft.strength > current.strength:
                    by_key[key] = draft

    return tuple(by_key.values())


def _add_instrument_mention(
    *,
    by_key: dict[tuple[str, StableId], _InstrumentMentionDraft],
    sentence: SentenceRecord,
    raw_value: str,
    normalized_name: str,
    base_strength: int,
    context_bonus: int,
    context_penalty: int,
) -> None:
    normalized = _normalize_instrument_name_candidate(raw_value)
    if normalized != normalized_name:
        normalized = normalized_name
    if _is_false_instrument_candidate(normalized, sentence):
        return

    strength = max(base_strength + context_bonus + context_penalty, 1)
    key = (normalized, sentence.id)
    draft = _InstrumentMentionDraft(
        normalized_name=normalized,
        raw_text=raw_value,
        evidence_span_id=sentence.id,
        strength=strength,
    )
    current = by_key.get(key)
    if current is None or draft.strength > current.strength:
        by_key[key] = draft


def _extract_instrument_name(
    file_path: str,
    sentences: tuple[SentenceRecord, ...],
) -> ContextFieldExtraction:
    drafts: list[_CandidateDraft] = []
    patterns = (
        _INSTRUMENT_LABEL_RE,
        re.compile(r"\busing (?:the )?([A-Z][A-Za-z0-9\-_/]*(?: [A-Za-z0-9\-_/]+){0,4})"),
    )

    for sentence in sentences:
        if _is_reference_sentence(sentence):
            continue

        text = sentence.provenance.raw_text
        for pattern in patterns:
            match = pattern.search(text)
            if not match:
                continue
            value = _normalize_instrument_name_candidate(match.group(1))
            if _NOT_REPORTED_RE.search(value):
                continue
            if not value:
                continue
            if _is_false_instrument_candidate(value, sentence):
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
    explicit_pattern = re.compile(
        r"target\s+population\s*[:=-]?\s*([A-Za-z][A-Za-z0-9\-_/(), ]+)",
        flags=re.IGNORECASE,
    )
    transfemoral_pattern = re.compile(
        r"\b(?:participants?|patients?)\b[^.]{0,160}\btransfemoral\s+amputation(?:s)?\b[^.]{0,120}",
        flags=re.IGNORECASE,
    )

    for sentence in sentences:
        if _is_reference_sentence(sentence):
            continue

        text = sentence.provenance.raw_text
        text_lower = text.lower()

        explicit_match = explicit_pattern.search(text)
        if explicit_match:
            value = _normalize_text_value(explicit_match.group(1))
            if not _NOT_REPORTED_RE.search(value) and value:
                drafts.append(
                    _CandidateDraft(
                        raw_text=explicit_match.group(0),
                        normalized_value=value,
                        evidence_span_id=sentence.id,
                    )
                )
            continue

        if "transfemoral" not in text_lower:
            continue
        if "amputation" not in text_lower:
            continue

        fallback_match = transfemoral_pattern.search(text)
        if not fallback_match:
            continue

        segment = _normalize_text_value(fallback_match.group(0))
        if "osseointegration" in text_lower or "osseointegrat" in text_lower:
            drafts.append(
                _CandidateDraft(
                    raw_text=fallback_match.group(0),
                    normalized_value=segment,
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
        ("prospective, observational clinical study", "prospective_observational_study"),
        ("prospective, observational trial", "prospective_observational_study"),
        ("prospective observational clinical study", "prospective_observational_study"),
        ("prospective observational trial", "prospective_observational_study"),
        ("cross-sectional validation study", "cross_sectional_validation_study"),
        ("longitudinal cohort", "longitudinal_cohort"),
        ("randomized controlled trial", "randomized_controlled_trial"),
        ("cross-sectional", "cross_sectional"),
        ("cohort", "cohort"),
        ("case-control", "case_control"),
        ("longitudinal", "longitudinal"),
        ("validation study", "validation_study"),
        ("prospective", "prospective"),
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

    for sentence in sentences:
        text = sentence.provenance.raw_text
        if "subsample" in text.lower():
            continue
        for match in _SAMPLE_SIZE_N_RE.finditer(text):
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


def _extract_sample_size_observations(
    file_path: str,
    sentences: tuple[SentenceRecord, ...],
    sample_sizes: ContextFieldExtraction,
) -> tuple[SampleSizeObservation, ...]:
    drafts: list[_SampleSizeDraft] = []

    for sentence in sentences:
        if _is_reference_sentence(sentence):
            continue

        text = sentence.provenance.raw_text
        for pattern in _ENROLLMENT_PATTERNS:
            for match in pattern.finditer(text):
                drafts.append(
                    _SampleSizeDraft(
                        role=SampleSizeRole.ENROLLMENT,
                        raw_text=match.group(0),
                        normalized_value=int(match.group(1)),
                        unit="participants",
                        evidence_span_id=sentence.id,
                    )
                )

        for pattern in _ANALYZED_PATTERNS:
            for match in pattern.finditer(text):
                drafts.append(
                    _SampleSizeDraft(
                        role=SampleSizeRole.ANALYZED,
                        raw_text=match.group(0),
                        normalized_value=int(match.group(1)),
                        unit="participants",
                        evidence_span_id=sentence.id,
                    )
                )

        for pattern in _LIMB_LEVEL_PATTERNS:
            for match in pattern.finditer(text):
                drafts.append(
                    _SampleSizeDraft(
                        role=SampleSizeRole.LIMB_LEVEL,
                        raw_text=match.group(0),
                        normalized_value=int(match.group(1)),
                        unit="limbs",
                        evidence_span_id=sentence.id,
                    )
                )

    # Backward-compatible fallback for fixtures with only generic N statements.
    if not drafts and sample_sizes.candidates:
        for candidate in sample_sizes.candidates:
            if isinstance(candidate.normalized_value, int):
                for evidence_span_id in candidate.evidence_span_ids:
                    drafts.append(
                        _SampleSizeDraft(
                            role=SampleSizeRole.OTHER,
                            raw_text=candidate.raw_text,
                            normalized_value=candidate.normalized_value,
                            unit="participants",
                            evidence_span_id=evidence_span_id,
                        )
                    )

    grouped: dict[tuple[SampleSizeRole, int, str | None], list[_SampleSizeDraft]] = defaultdict(
        list
    )
    for draft in drafts:
        grouped[(draft.role, draft.normalized_value, draft.unit)].append(draft)

    observations: list[SampleSizeObservation] = []
    for key in sorted(grouped, key=lambda item: (item[0].value, item[1], item[2] or "")):
        role, value, unit = key
        group = grouped[key]
        evidence_span_ids = tuple(dict.fromkeys(record.evidence_span_id for record in group))
        raw_text = " || ".join(dict.fromkeys(record.raw_text for record in group))
        observations.append(
            SampleSizeObservation(
                id=_stable_id(
                    "samplerole",
                    file_path,
                    role.value,
                    value,
                    unit or "",
                    *evidence_span_ids,
                ),
                role=role,
                sample_size_raw=raw_text,
                sample_size_normalized=value,
                unit=unit,
                evidence_span_ids=evidence_span_ids,
            )
        )

    return tuple(observations)


def _extract_follow_up_schedule(
    file_path: str,
    sentences: tuple[SentenceRecord, ...],
) -> ContextFieldExtraction:
    drafts: list[_CandidateDraft] = []

    for sentence in sentences:
        text = sentence.provenance.raw_text
        text_lower = text.lower()

        if (
            "follow-up" not in text_lower
            and "baseline" not in text_lower
            and "before surgery" not in text_lower
        ):
            continue

        schedule_tokens: list[str] = []
        if "baseline" in text_lower or "before surgery" in text_lower:
            schedule_tokens.append("baseline")

        for match in _INTERVAL_RE.finditer(text_lower):
            amount = match.group(1)
            unit = match.group(2)
            normalized_unit = unit if unit.endswith("s") else f"{unit}s"
            schedule_tokens.append(f"{amount} {normalized_unit}")

        deduplicated = tuple(dict.fromkeys(schedule_tokens))
        if len(deduplicated) < 2:
            continue

        drafts.append(
            _CandidateDraft(
                raw_text=text,
                normalized_value=deduplicated,
                evidence_span_id=sentence.id,
            )
        )

    return _build_field_extraction(
        file_path,
        "follow_up_schedule",
        drafts,
        _collect_not_reported_candidates(
            field_aliases=("follow-up", "follow up", "baseline"),
            sentences=sentences,
        ),
    )


def _extract_measurement_property_partitions(
    file_path: str,
    sentences: tuple[SentenceRecord, ...],
) -> tuple[ContextFieldExtraction, ContextFieldExtraction, ContextFieldExtraction]:
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

    direct_values: set[str] = set()
    background_values: set[str] = set()
    interpretability_values: set[str] = set()

    direct_evidence: list[_CandidateDraft] = []
    background_evidence: list[_CandidateDraft] = []
    interpretability_evidence: list[_CandidateDraft] = []

    for sentence in sentences:
        if _is_reference_sentence(sentence):
            continue

        text = sentence.provenance.raw_text
        text_lower = text.lower()

        found_here: set[str] = set()
        for needle, normalized in property_needles:
            if needle in text_lower:
                found_here.add(normalized)

        if not found_here:
            continue

        if _is_interpretability_sentence(text_lower):
            interpretability_values.update(found_here)
            interpretability_evidence.append(
                _CandidateDraft(
                    raw_text=text,
                    normalized_value=tuple(sorted(found_here)),
                    evidence_span_id=sentence.id,
                )
            )
            continue

        if _is_background_sentence(sentence):
            background_values.update(found_here)
            background_evidence.append(
                _CandidateDraft(
                    raw_text=text,
                    normalized_value=tuple(sorted(found_here)),
                    evidence_span_id=sentence.id,
                )
            )
            continue

        direct_values.update(found_here)
        direct_evidence.append(
            _CandidateDraft(
                raw_text=text,
                normalized_value=tuple(sorted(found_here)),
                evidence_span_id=sentence.id,
            )
        )

    direct_field = _build_property_field(
        file_path=file_path,
        field_name="measurement_properties_mentioned",
        values=direct_values,
        evidence=direct_evidence,
        not_reported_candidates=_collect_not_reported_candidates(
            field_aliases=("measurement propert", "property"),
            sentences=sentences,
        ),
    )
    background_field = _build_property_field(
        file_path=file_path,
        field_name="measurement_properties_background",
        values=background_values,
        evidence=background_evidence,
        not_reported_candidates=[],
    )
    interpretability_field = _build_property_field(
        file_path=file_path,
        field_name="measurement_properties_interpretability",
        values=interpretability_values,
        evidence=interpretability_evidence,
        not_reported_candidates=[],
    )

    return direct_field, background_field, interpretability_field


def _build_property_field(
    *,
    file_path: str,
    field_name: str,
    values: set[str],
    evidence: list[_CandidateDraft],
    not_reported_candidates: list[_CandidateDraft],
) -> ContextFieldExtraction:
    drafts: list[_CandidateDraft] = []
    if values and evidence:
        drafts.append(
            _CandidateDraft(
                raw_text=" || ".join(dict.fromkeys(item.raw_text for item in evidence)),
                normalized_value=tuple(sorted(values)),
                evidence_span_id=evidence[0].evidence_span_id,
            )
        )

    return _build_field_extraction(
        file_path,
        field_name,
        drafts,
        not_reported_candidates,
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


def _normalize_instrument_name_candidate(raw_value: str) -> str:
    value = _normalize_text_value(raw_value).strip("()")
    value_lower = value.lower()

    if not value:
        return ""
    if _QTFA_FULL_RE.search(value) or _QTFA_ABBR_RE.search(value):
        return "Q-TFA"
    if _PROMIS_FULL_RE.search(value) or _PROMIS_ABBR_RE.search(value):
        return "PROMIS"

    # Keep short uppercase/hyphenated tokens stable (PROM-X, ABC-12).
    if value.isupper() or re.fullmatch(r"[A-Z][A-Z0-9]+(?:-[A-Z0-9]+)+", value):
        return value

    # Remove leading determiners in generic phrases.
    if value_lower.startswith("the "):
        value = value[4:]

    return _normalize_text_value(value)


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


def _first_candidate_normalized(field: ContextFieldExtraction) -> str | None:
    if not field.candidates:
        return None
    normalized = field.candidates[0].normalized_value
    if isinstance(normalized, str):
        return normalized
    return None


def _is_reference_sentence(sentence: SentenceRecord) -> bool:
    heading_tokens = " ".join(sentence.heading_path).lower()
    return "references" in heading_tokens or "acknowledg" in heading_tokens


def _is_background_sentence(sentence: SentenceRecord) -> bool:
    text = sentence.provenance.raw_text
    text_lower = text.lower()
    heading_tokens = " ".join(sentence.heading_path).lower()

    if _is_reference_sentence(sentence):
        return True
    if _CITATION_RE.search(text) and any(
        token in text_lower
        for token in (
            "validity",
            "reliability",
            "validated",
            "demonstrated",
            "previous",
            "prior",
        )
    ):
        return True
    if "introduction" in heading_tokens and _CITATION_RE.search(text):
        return True
    return "discussion" in heading_tokens and _CITATION_RE.search(text) is not None


def _is_interpretability_sentence(text_lower: str) -> bool:
    return any(
        token in text_lower
        for token in (
            "mcid",
            "mic",
            "mid",
            "minimum clinically important difference",
            "minimal clinically important difference",
            "minimal detectable change",
            "interpret",
            "anchor-based",
            "distribution method",
        )
    )


def _is_false_instrument_candidate(value: str, sentence: SentenceRecord) -> bool:
    value_lower = value.lower()
    sentence_lower = sentence.provenance.raw_text.lower()

    if _is_reference_sentence(sentence):
        return True

    banned_tokens = {
        "opra",
        "opra system",
        "osseointegrated prostheses for the rehabilitation of amputees",
        "osseoanchored prostheses for the rehabilitation of amputees",
        "integrum",
        "amputee coalition",
        "walter reed",
        "medical center",
        "r core team",
        "hud",
        "fda",
    }
    if value_lower in banned_tokens:
        return True
    if any(token in value_lower for token in ("implant", "device", "system", "calculator")):
        return True
    if _NON_INSTRUMENT_CONTEXT_RE.search(sentence_lower) and not _INSTRUMENT_CONTEXT_RE.search(
        sentence_lower
    ):
        return True
    return len(value) <= 2


def _stable_id(prefix: str, *parts: object) -> StableId:
    serialized = "|".join(str(part) for part in parts)
    digest = hashlib.sha1(f"{prefix}|{serialized}".encode()).hexdigest()[:16]
    return f"{prefix}.{digest}"
