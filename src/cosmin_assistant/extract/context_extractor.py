"""Deterministic first-pass extraction of study and instrument context fields."""

from __future__ import annotations

import hashlib
import os
import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from cosmin_assistant.extract.context_models import (
    ArticleContextExtractionResult,
    ContextFieldExtraction,
    ContextValueCandidate,
    FieldDetectionStatus,
    InstrumentContextExtractionResult,
    InstrumentContextRole,
    SampleSizeObservation,
    SampleSizeRole,
    StudyContextExtractionResult,
    StudyIntent,
    SubsampleExtraction,
)
from cosmin_assistant.extract.markdown_parser import parse_markdown_file
from cosmin_assistant.extract.spans import ParsedMarkdownDocument, SentenceRecord
from cosmin_assistant.models.base import StableId
from cosmin_assistant.models.enums import InstrumentType

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
    r"instrument|questionnaire|scale|survey|test|measure|measures|patient-reported|"
    r"outcome|outcome measure|domain score|scores?|completed|baseline|follow-up"
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
    r"([A-Za-z][A-Za-z0-9\-_/(). ]{1,120})",
    flags=re.IGNORECASE,
)
_OUTCOME_LIST_RE = re.compile(
    r"\b(?:outcome\s+measures?|outcomes?)\s*(?:include(?:d)?|consisted\s+of|"
    r"were\s+assessed\s+with|were\s+measured\s+with|were\s+the)\s*[:=-]?\s*([^.]+)",
    flags=re.IGNORECASE,
)
_INSTRUMENT_ACRONYM_RE = re.compile(
    r"\b([A-Z][A-Z0-9]+(?:-[A-Z0-9]+)+|[A-Z]{3,12}(?:\s*\d+(?:\.\d+)*)?)\b"
)
_SIGAM_FULL_RE = re.compile(r"special\s+interest\s+group\s+in\s+amputee\s+medicine", re.IGNORECASE)
_SIGAM_ABBR_RE = re.compile(r"\bsigam\b", re.IGNORECASE)
_LCI5_FULL_RE = re.compile(r"locomotor\s+capabilities\s+index-?5", re.IGNORECASE)
_LCI5_ABBR_RE = re.compile(r"\blci-?5\b", re.IGNORECASE)
_HOUGHTON_RE = re.compile(r"\bhoughton(?:\s+scale)?\b", re.IGNORECASE)
_ABC_FULL_RE = re.compile(r"activities-?specific\s+balance\s+confidence", re.IGNORECASE)
_ABC_ABBR_RE = re.compile(r"\babc(?:\s+scale)?\b", re.IGNORECASE)
_GPS_FULL_RE = re.compile(r"\bgait\s+profile\s+score\b", re.IGNORECASE)
_GPS_ABBR_RE = re.compile(r"\bgps\b", re.IGNORECASE)
_TWO_MWT_FULL_RE = re.compile(r"two[- ]?minute\s+walk\s+test", re.IGNORECASE)
_TWO_MWT_ABBR_RE = re.compile(r"\b2-?mwt\b", re.IGNORECASE)
_TUG_FULL_RE = re.compile(r"timed\s+up\s+and\s+go", re.IGNORECASE)
_TUG_ABBR_RE = re.compile(
    r"(?<![A-Za-z0-9-])tug(?:\s+test)?(?![A-Za-z0-9-])",
    re.IGNORECASE,
)
_COLD_TUG_FULL_RE = re.compile(
    r"colorado\s+limb\s+donning[- ]timed\s+up\s+and\s+go",
    re.IGNORECASE,
)
_COLD_TUG_ABBR_RE = re.compile(r"\bcold-?tug\b", re.IGNORECASE)
_SIX_MWT_FULL_RE = re.compile(r"\b6[- ]?minute\s+walk\s+test\b", re.IGNORECASE)
_SIX_MWT_ABBR_RE = re.compile(r"\b6[- ]?mwt\b", re.IGNORECASE)
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
_CITATION_RE = re.compile(
    r"\[[0-9,\s]+\]|<sup>\s*\d+(?:\s*[-,]\s*\d+)*\s*</sup>|\bet\s+al\.\b",
    flags=re.IGNORECASE,
)
_INTERVAL_RE = re.compile(r"\b(\d+)\s*(month|months|week|weeks|year|years)\b", flags=re.IGNORECASE)
_FOLLOW_UP_INTERVAL_WORD_RE = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s*[- ]?"
    r"(day|days|week|weeks|month|months|year|years)\b",
    flags=re.IGNORECASE,
)
_SOFTWARE_VERSION_CONTEXT_RE = re.compile(
    r"\b(?:spss|stata|sas|r\s+software|python|jamovi|matlab)\b",
    flags=re.IGNORECASE,
)
_INSTRUMENT_VERSION_CONTEXT_RE = re.compile(
    r"\b(?:instrument|questionnaire|scale|measure|tool|test|form)\b",
    flags=re.IGNORECASE,
)
_INTERNAL_STRUCTURE_SIGNAL_RE = re.compile(
    r"\b(?:rasch|irt|item\s+fit|infit|outfit|local\s+dependence|"
    r"local\s+independence|unidimensional(?:ity)?|dimensionality|"
    r"residual\s+pca|threshold\s+ordering)\b",
    flags=re.IGNORECASE,
)
_RECRUITMENT_SETTING_RE = re.compile(
    r"(?:recruited|enrolled|included)[^.]{0,220}\bfrom\b[^.]{0,220}",
    flags=re.IGNORECASE,
)
_AURORA_SETTING_RE = re.compile(
    r"(?:university\s+of\s+colorado|aurora,\s*colorado|anschutz)",
    flags=re.IGNORECASE,
)
_VALIDATION_SAMPLE_RE = re.compile(
    r"\b(?:sample size of|validity study[^.]{0,80}\bof|"
    r"validation study[^.]{0,80}\bof|administered to)\s+"
    r"(forty|thirty|twenty|ten|\d+)\b",
    flags=re.IGNORECASE,
)
_VALIDITY_STUDY_SAMPLE_RE = re.compile(
    r"\b(\d+)\s+(?:participants?|patients?|subjects?)?\s*(?:in|for)\s+(?:the\s+)?"
    r"(?:validity|validation)\s+study\b",
    flags=re.IGNORECASE,
)
_ANALYZED_OBSERVATIONS_RE = re.compile(
    r"\btotal\s+of\s+(\d+)\s+data\s+points?\b[^.]{0,80}\banaly",
    flags=re.IGNORECASE,
)
_PILOT_SAMPLE_RE = re.compile(
    r"\bpilot(?:-tested| study)?[^.]{0,100}\b[nN]\s*=\s*(\d+)\b",
    flags=re.IGNORECASE,
)
_RETEST_SAMPLE_RE = re.compile(
    r"\b(?:test-?retest|retest)[^.]{0,120}\b(?:n\s*=\s*(\d+)|(\d+)\s+participants?)\b",
    flags=re.IGNORECASE,
)
_RELIABILITY_STUDY_SAMPLE_RE = re.compile(
    r"\b(\d+)\s+(?:participants?|patients?|subjects?)?\s*(?:in|for)\s+(?:the\s+)?"
    r"reliability\s+study\b",
    flags=re.IGNORECASE,
)
_BAL_GROUP_SAMPLE_RE = re.compile(
    r"\b(?:bal\s+(?:users|participants)|bone-anchored\s+limb\s+group)\b[^.]{0,80}\(\s*[nN]\s*=\s*(\d+)\s*\)",
    flags=re.IGNORECASE,
)
_TARGET_POPULATION_RE = re.compile(
    r"\b(?:adults?|participants?|individuals?|people|patients?)\s+with\s+"
    r"(lower\s+limb\s+amputation(?:s)?|transfemoral\s+amputation(?:s)?)\b",
    flags=re.IGNORECASE,
)
_UNILATERAL_LOWER_EXTREMITY_RE = re.compile(
    r"\b(?:individuals?|participants?)\s+with\s+unilateral\s+lower-?extremity\s+amputation\b",
    flags=re.IGNORECASE,
)
_LANGUAGE_CANONICAL: dict[str, str] = {
    "english": "English",
    "dutch": "Dutch",
    "french": "French",
    "turkish": "Turkish",
    "persian": "Persian",
}
_COUNTRY_CANONICAL: dict[str, str] = {
    "colorado": "United States",
    "iran": "Iran",
    "netherlands": "Netherlands",
    "belgium": "Belgium",
    "france": "France",
    "turkey": "Turkey",
    "united states": "United States",
    "usa": "United States",
    "u.s.a.": "United States",
    "u.s.": "United States",
}
_NUMBER_WORDS: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
}
_TARGET_PRIORITY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:aim|objective)\b[^.]{0,180}\b(?:develop|validation|validity|reliability)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\btranslated\b[^.]{0,200}\b(psychometric|validation|cross-cultural|adapt)", re.IGNORECASE
    ),
    re.compile(
        r"\b(psychometric properties|internal consistency|test-?retest|construct validity)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bobjective of this study\b", re.IGNORECASE),
)
_PARENTHETICAL_ACRONYM_RE = re.compile(r"\(([A-Z][A-Z0-9\-]*(?:\s+\d+(?:\.\d+)*)?)\)")
_COMPARATOR_CONTEXT_RE = re.compile(
    r"\b(by comparing|compared with|comparison(?:s)? with|correlation(?:s)? (?:between|with)|"
    r"correlated with|association (?:between|with))\b",
    re.IGNORECASE,
)
_GOLD_STANDARD_RE = re.compile(r"\bgold standard\b", re.IGNORECASE)
_ENROLLMENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\ba\s+total\s+of\s+(\d+)\s+(?:participants?|patients?|subjects?)\s+were\s+"
        r"(?:recruited|enrolled|included)\b",
        flags=re.IGNORECASE,
    ),
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
    _ANALYZED_OBSERVATIONS_RE,
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


@dataclass(frozen=True)
class _NumberToken:
    raw_text: str
    value: int


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
    validation_sample_n = _extract_validation_sample_n(parsed.file_path, sentences)
    pilot_sample_n = _extract_pilot_sample_n(parsed.file_path, sentences)
    retest_sample_n = _extract_retest_sample_n(
        parsed.file_path,
        sentences,
        validation_sample_n=validation_sample_n,
    )
    sample_size_observations = _extract_sample_size_observations(
        parsed.file_path,
        sentences,
        sample_sizes,
        validation_sample_n=validation_sample_n,
        pilot_sample_n=pilot_sample_n,
        retest_sample_n=retest_sample_n,
    )
    follow_up_schedule = _extract_follow_up_schedule(parsed.file_path, sentences)
    follow_up_interval = _extract_follow_up_interval(parsed.file_path, sentences)
    recruitment_setting = _extract_recruitment_setting(parsed.file_path, sentences)
    (
        measurement_properties,
        measurement_properties_background,
        measurement_properties_interpretability,
        measurement_properties_not_assessed,
    ) = _extract_measurement_property_partitions(parsed.file_path, sentences)
    subsamples = _extract_subsamples(parsed.file_path, sentences)
    study_intent, study_intent_rationale, study_intent_evidence_span_ids = _classify_study_intent(
        sentences=sentences
    )

    study_context = StudyContextExtractionResult(
        id=_stable_id("studyctx", parsed.id, study_id),
        article_id=parsed.id,
        study_id=study_id,
        study_design=study_design,
        sample_sizes=sample_sizes,
        sample_size_observations=sample_size_observations,
        validation_sample_n=validation_sample_n,
        pilot_sample_n=pilot_sample_n,
        retest_sample_n=retest_sample_n,
        follow_up_schedule=follow_up_schedule,
        follow_up_interval=follow_up_interval,
        construct_field=construct,
        target_population=target_population,
        recruitment_setting=recruitment_setting,
        language=language,
        country=country,
        measurement_properties_mentioned=measurement_properties,
        measurement_properties_background=measurement_properties_background,
        measurement_properties_interpretability=measurement_properties_interpretability,
        measurement_properties_not_assessed=measurement_properties_not_assessed,
        study_intent=study_intent,
        study_intent_rationale=study_intent_rationale,
        study_intent_evidence_span_ids=study_intent_evidence_span_ids,
        subsamples=subsamples,
    )

    instrument_contexts, target_instrument_id, comparator_instrument_ids = (
        _build_instrument_contexts(
            article_id=parsed.id,
            study_id=study_id,
            file_path=parsed.file_path,
            sentences=sentences,
            instrument_name_fields=instrument_name_fields,
            instrument_version=instrument_version,
            subscale=subscale,
            construct=construct,
            target_population=target_population,
            study_intent=study_intent,
        )
    )

    return ArticleContextExtractionResult(
        id=_stable_id("articlectx", parsed.id, parsed.file_path),
        article_id=parsed.id,
        file_path=parsed.file_path,
        study_contexts=(study_context,),
        instrument_contexts=instrument_contexts,
        target_instrument_id=target_instrument_id,
        comparator_instrument_ids=comparator_instrument_ids,
    )


def _build_instrument_contexts(
    *,
    article_id: StableId,
    study_id: StableId,
    file_path: str,
    sentences: tuple[SentenceRecord, ...],
    instrument_name_fields: tuple[ContextFieldExtraction, ...],
    instrument_version: ContextFieldExtraction,
    subscale: ContextFieldExtraction,
    construct: ContextFieldExtraction,
    target_population: ContextFieldExtraction,
    study_intent: StudyIntent,
) -> tuple[
    tuple[InstrumentContextExtractionResult, ...],
    StableId | None,
    tuple[StableId, ...],
]:
    contexts: list[InstrumentContextExtractionResult] = []
    normalized_by_instrument_id: dict[StableId, str] = {}

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
        instrument_type, type_rationale, type_evidence_span_ids = _classify_instrument_type(
            normalized_name=discriminator,
            sentences=sentences,
        )
        normalized_by_instrument_id[instrument_id] = discriminator
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
                instrument_type=instrument_type,
                instrument_type_rationale=type_rationale,
                instrument_type_evidence_span_ids=type_evidence_span_ids,
            )
        )

    if not contexts:
        return (), None, ()

    role_assignments = _infer_instrument_roles(
        sentences=sentences,
        study_intent=study_intent,
        normalized_instrument_names=tuple(
            (context.instrument_id, normalized_by_instrument_id[context.instrument_id])
            for context in contexts
        ),
    )
    enriched_contexts: list[InstrumentContextExtractionResult] = []
    comparator_ids: list[StableId] = []
    target_id: StableId | None = None
    for context in contexts:
        role, rationale, role_evidence_span_ids = role_assignments.get(
            context.instrument_id,
            (
                InstrumentContextRole.BACKGROUND_ONLY,
                "No strong role signal detected.",
                (),
            ),
        )
        if (
            role
            in (
                InstrumentContextRole.TARGET_UNDER_APPRAISAL,
                InstrumentContextRole.CO_PRIMARY_OUTCOME_INSTRUMENT,
            )
            and target_id is None
        ):
            target_id = context.instrument_id
        if role in (InstrumentContextRole.COMPARATOR, InstrumentContextRole.COMPARATOR_ONLY):
            comparator_ids.append(context.instrument_id)
        enriched_contexts.append(
            context.model_copy(
                update={
                    "instrument_role": role,
                    "role_rationale": rationale,
                    "role_evidence_span_ids": role_evidence_span_ids,
                }
            )
        )

    if target_id is None:
        target_id = enriched_contexts[0].instrument_id
        first = enriched_contexts[0]
        enriched_contexts[0] = first.model_copy(
            update={
                "instrument_role": InstrumentContextRole.TARGET_UNDER_APPRAISAL,
                "role_rationale": "Fallback target: highest-priority extracted instrument context.",
                "role_evidence_span_ids": first.role_evidence_span_ids,
            }
        )

    return tuple(enriched_contexts), target_id, tuple(dict.fromkeys(comparator_ids))


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
        if mention_count < 2 and strongest < 5:
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
        if _is_reference_sentence(sentence) or _is_keyword_sentence(sentence):
            continue

        text = sentence.provenance.raw_text
        context_bonus = 2 if _INSTRUMENT_CONTEXT_RE.search(text) else 0
        context_penalty = -3 if _NON_INSTRUMENT_CONTEXT_RE.search(text) else 0

        if _SIGAM_FULL_RE.search(text):
            _add_instrument_mention(
                by_key=by_key,
                sentence=sentence,
                raw_value="SIGAM",
                normalized_name="SIGAM",
                base_strength=5,
                context_bonus=context_bonus,
                context_penalty=context_penalty,
            )
        for match in _SIGAM_ABBR_RE.finditer(text):
            _add_instrument_mention(
                by_key=by_key,
                sentence=sentence,
                raw_value=match.group(0),
                normalized_name="SIGAM",
                base_strength=4,
                context_bonus=context_bonus,
                context_penalty=context_penalty,
            )

        if _LCI5_FULL_RE.search(text):
            _add_instrument_mention(
                by_key=by_key,
                sentence=sentence,
                raw_value="Locomotor Capabilities Index-5",
                normalized_name="LCI-5",
                base_strength=4,
                context_bonus=context_bonus,
                context_penalty=context_penalty,
            )
        for match in _LCI5_ABBR_RE.finditer(text):
            _add_instrument_mention(
                by_key=by_key,
                sentence=sentence,
                raw_value=match.group(0),
                normalized_name="LCI-5",
                base_strength=3,
                context_bonus=context_bonus,
                context_penalty=context_penalty,
            )

        if _HOUGHTON_RE.search(text):
            _add_instrument_mention(
                by_key=by_key,
                sentence=sentence,
                raw_value="Houghton scale",
                normalized_name="Houghton",
                base_strength=3,
                context_bonus=context_bonus,
                context_penalty=context_penalty,
            )
        if _ABC_FULL_RE.search(text) or _ABC_ABBR_RE.search(text):
            _add_instrument_mention(
                by_key=by_key,
                sentence=sentence,
                raw_value="ABC scale",
                normalized_name="ABC",
                base_strength=3,
                context_bonus=context_bonus,
                context_penalty=context_penalty,
            )
        if _GPS_FULL_RE.search(text) or _GPS_ABBR_RE.search(text):
            _add_instrument_mention(
                by_key=by_key,
                sentence=sentence,
                raw_value="GPS",
                normalized_name="GPS",
                base_strength=3,
                context_bonus=context_bonus,
                context_penalty=context_penalty,
            )
        if _TWO_MWT_FULL_RE.search(text) or _TWO_MWT_ABBR_RE.search(text):
            _add_instrument_mention(
                by_key=by_key,
                sentence=sentence,
                raw_value="2-MWT",
                normalized_name="2-MWT",
                base_strength=3,
                context_bonus=context_bonus,
                context_penalty=context_penalty,
            )
        if _TUG_FULL_RE.search(text) or _TUG_ABBR_RE.search(text):
            _add_instrument_mention(
                by_key=by_key,
                sentence=sentence,
                raw_value="TUG",
                normalized_name="TUG",
                base_strength=3,
                context_bonus=context_bonus,
                context_penalty=context_penalty,
            )
        if _COLD_TUG_FULL_RE.search(text) or _COLD_TUG_ABBR_RE.search(text):
            _add_instrument_mention(
                by_key=by_key,
                sentence=sentence,
                raw_value="COLD-TUG",
                normalized_name="COLD-TUG",
                base_strength=5,
                context_bonus=context_bonus,
                context_penalty=context_penalty,
            )
        if _SIX_MWT_FULL_RE.search(text) or _SIX_MWT_ABBR_RE.search(text):
            _add_instrument_mention(
                by_key=by_key,
                sentence=sentence,
                raw_value="6-MWT",
                normalized_name="6-MWT",
                base_strength=3,
                context_bonus=context_bonus,
                context_penalty=context_penalty,
            )

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
            raw_items = _split_outcome_or_instrument_list(match.group(1))
            if not raw_items:
                raw_items = (match.group(1),)
            for raw_item in raw_items:
                value = _normalize_instrument_name_candidate(raw_item)
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

        outcome_list_match = _OUTCOME_LIST_RE.search(text)
        if outcome_list_match:
            for item in _split_outcome_or_instrument_list(outcome_list_match.group(1)):
                value = _normalize_instrument_name_candidate(item)
                if not value:
                    continue
                if _is_false_instrument_candidate(value, sentence):
                    continue
                key = (value, sentence.id)
                draft = _InstrumentMentionDraft(
                    normalized_name=value,
                    raw_text=item,
                    evidence_span_id=sentence.id,
                    strength=max(3 + context_bonus + context_penalty, 1),
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
                if not (
                    "-" in value
                    or value.startswith("PROM")
                    or value in {"SIGAM", "ABC", "TUG"}
                    or re.search(r"\d+\.\d+", token)
                ):
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
        if _INSTRUMENT_CONTEXT_RE.search(text) and "(" in text and ")" in text:
            for token in re.findall(r"\(([A-Za-z0-9\- .]{2,20})\)", text):
                compact_token = token.strip()
                if len(compact_token.split()) > 2:
                    continue
                if not re.search(r"[A-Z]{2,}", compact_token):
                    continue
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
                    strength=max(3 + context_bonus + context_penalty, 1),
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
        if _is_reference_sentence(sentence) or _is_background_sentence(sentence):
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
        r"(?:(instrument|questionnaire|scale|measure|tool|test|form)\s+version|version|\bv)"
        r"\s*[:=-]?\s*(v?\d+(?:\.\d+)*)",
        flags=re.IGNORECASE,
    )

    for sentence in sentences:
        if _is_reference_sentence(sentence) or _is_background_sentence(sentence):
            continue
        text = sentence.provenance.raw_text
        text_lower = text.lower()
        if _SOFTWARE_VERSION_CONTEXT_RE.search(text):
            continue
        match = pattern.search(text)
        if not match:
            continue
        explicit_instrument_prefix = match.group(1)
        if explicit_instrument_prefix is None and not _INSTRUMENT_VERSION_CONTEXT_RE.search(text):
            continue
        if "statistical analysis" in text_lower and "version" in text_lower:
            continue
        normalized = _normalize_version(match.group(2))
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
        r"\b(?:participants?|patients?)\b(?!-)[^.]{0,160}"
        r"\btransfemoral\s+amputation(?:s)?\b[^.]{0,120}",
        flags=re.IGNORECASE,
    )

    for sentence in sentences:
        if _is_reference_sentence(sentence) or _is_background_sentence(sentence):
            continue

        text = sentence.provenance.raw_text
        text_lower = text.lower()
        if _is_question_like_text(text):
            continue

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

        target_match = _TARGET_POPULATION_RE.search(text)
        if target_match:
            normalized = _normalize_text_value(f"adults with {target_match.group(1)}")
            if (
                "transfemoral amputation" in target_match.group(1).lower()
                and "osseointegr" in text_lower
            ):
                normalized = (
                    "adults with transfemoral amputation " "undergoing osseointegration surgery"
                )
            drafts.append(
                _CandidateDraft(
                    raw_text=target_match.group(0),
                    normalized_value=normalized,
                    evidence_span_id=sentence.id,
                )
            )
            continue

        unilateral_match = _UNILATERAL_LOWER_EXTREMITY_RE.search(text)
        if unilateral_match:
            normalized = (
                "adults with unilateral lower-extremity amputation using socket prosthesis or BAL"
            )
            drafts.append(
                _CandidateDraft(
                    raw_text=unilateral_match.group(0),
                    normalized_value=normalized,
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
            segment = "adults with transfemoral amputation undergoing osseointegration surgery"
            drafts.append(
                _CandidateDraft(
                    raw_text=fallback_match.group(0),
                    normalized_value=segment,
                    evidence_span_id=sentence.id,
                )
            )
            continue
        if not segment.lower().startswith("adults with"):
            segment = f"adults with {segment}"
        drafts.append(
            _CandidateDraft(
                raw_text=fallback_match.group(0),
                normalized_value=segment,
                evidence_span_id=sentence.id,
            )
        )

    drafts = _prefer_specific_target_population(drafts)

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

    for sentence in sentences:
        if _is_reference_sentence(sentence) or _is_background_sentence(sentence):
            continue
        text = sentence.provenance.raw_text
        text_lower = text.lower()
        if "@" in text_lower:
            continue

        for needle, canonical in _LANGUAGE_CANONICAL.items():
            if needle not in text_lower:
                continue
            if not any(
                token in text_lower
                for token in (
                    f"{needle} language",
                    f"into {needle}",
                    f"in {needle}",
                    f"{needle}-speaking",
                    "translated",
                )
            ) and not re.search(r"language\s*[:=-]", text_lower):
                continue
            drafts.append(
                _CandidateDraft(
                    raw_text=text,
                    normalized_value=canonical,
                    evidence_span_id=sentence.id,
                )
            )
            break

    drafts = _prefer_majority_value(drafts)

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

    for sentence in sentences:
        if _is_reference_sentence(sentence) or _is_background_sentence(sentence):
            continue
        text = sentence.provenance.raw_text
        text_lower = text.lower()
        if "@" in text_lower:
            continue
        if "disclaimer" in text_lower and "u.s." in text_lower:
            continue
        if "do not necessarily represent the views" in text_lower:
            continue
        for needle, canonical in _COUNTRY_CANONICAL.items():
            if re.search(rf"\b{re.escape(needle)}\b", text_lower):
                if needle == "colorado" and not _AURORA_SETTING_RE.search(text_lower):
                    continue
                drafts.append(
                    _CandidateDraft(
                        raw_text=text,
                        normalized_value=canonical,
                        evidence_span_id=sentence.id,
                    )
                )
                break

    drafts = _prefer_majority_value(drafts)

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
        (
            "prospective, cross-sectional study",
            "prospective_cross_sectional_validation_development_study",
        ),
        (
            "prospective cross-sectional study",
            "prospective_cross_sectional_validation_development_study",
        ),
        (
            "prospective, cross-sectional",
            "prospective_cross_sectional_validation_development_study",
        ),
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
        if _is_reference_sentence(sentence) or _is_background_sentence(sentence):
            continue
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

    drafts = _prefer_specific_study_design(drafts)

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
        if _is_reference_sentence(sentence) or _is_background_sentence(sentence):
            continue
        text = sentence.provenance.raw_text
        text_lower = text.lower()
        if _is_external_comparison_sentence(text_lower):
            continue
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
        for token in _extract_number_tokens(text):
            if token.value <= 0:
                continue
            if not any(
                marker in text.lower()
                for marker in ("participants", "patients", "sample", "study", "people")
            ):
                continue
            drafts.append(
                _CandidateDraft(
                    raw_text=token.raw_text,
                    normalized_value=token.value,
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


def _extract_validation_sample_n(
    file_path: str,
    sentences: tuple[SentenceRecord, ...],
) -> ContextFieldExtraction:
    drafts: list[_CandidateDraft] = []
    for sentence in sentences:
        if _is_reference_sentence(sentence) or _is_background_sentence(sentence):
            continue
        text = sentence.provenance.raw_text
        text_lower = text.lower()
        if _is_external_comparison_sentence(text_lower):
            continue
        if not any(
            token in text_lower
            for token in ("validation", "validity", "administered", "sample size")
        ):
            continue
        explicit_study_sample = _VALIDITY_STUDY_SAMPLE_RE.search(text)
        if explicit_study_sample:
            drafts.append(
                _CandidateDraft(
                    raw_text=explicit_study_sample.group(0),
                    normalized_value=int(explicit_study_sample.group(1)),
                    evidence_span_id=sentence.id,
                )
            )
            continue
        match = _VALIDATION_SAMPLE_RE.search(text)
        if match:
            value = _word_or_number_to_int(match.group(1))
            if value is not None:
                drafts.append(
                    _CandidateDraft(
                        raw_text=match.group(0),
                        normalized_value=value,
                        evidence_span_id=sentence.id,
                    )
                )
                continue
    drafts = _prefer_majority_value(drafts)

    return _build_field_extraction(
        file_path,
        "validation_sample_n",
        drafts,
        _collect_not_reported_candidates(
            field_aliases=("validation sample", "validity study", "sample size"),
            sentences=sentences,
        ),
    )


def _extract_pilot_sample_n(
    file_path: str,
    sentences: tuple[SentenceRecord, ...],
) -> ContextFieldExtraction:
    drafts: list[_CandidateDraft] = []
    for sentence in sentences:
        if _is_reference_sentence(sentence) or _is_background_sentence(sentence):
            continue
        text = sentence.provenance.raw_text
        if "pilot" not in text.lower():
            continue
        match = _PILOT_SAMPLE_RE.search(text)
        if not match:
            continue
        drafts.append(
            _CandidateDraft(
                raw_text=match.group(0),
                normalized_value=int(match.group(1)),
                evidence_span_id=sentence.id,
            )
        )

    return _build_field_extraction(
        file_path,
        "pilot_sample_n",
        drafts,
        _collect_not_reported_candidates(field_aliases=("pilot",), sentences=sentences),
    )


def _extract_retest_sample_n(
    file_path: str,
    sentences: tuple[SentenceRecord, ...],
    validation_sample_n: ContextFieldExtraction,
) -> ContextFieldExtraction:
    drafts: list[_CandidateDraft] = []
    validation_value = _first_int_candidate(validation_sample_n)
    for sentence in sentences:
        if _is_reference_sentence(sentence) or _is_background_sentence(sentence):
            continue
        text = sentence.provenance.raw_text
        text_lower = text.lower()
        if (
            "retest" not in text_lower
            and "test-retest" not in text_lower
            and "reliability study" not in text_lower
        ):
            continue
        reliability_study = _RELIABILITY_STUDY_SAMPLE_RE.search(text)
        if reliability_study:
            drafts.append(
                _CandidateDraft(
                    raw_text=reliability_study.group(0),
                    normalized_value=int(reliability_study.group(1)),
                    evidence_span_id=sentence.id,
                )
            )
            continue

        explicit = _RETEST_SAMPLE_RE.search(text)
        if explicit:
            value = explicit.group(1) or explicit.group(2)
            if value:
                drafts.append(
                    _CandidateDraft(
                        raw_text=explicit.group(0),
                        normalized_value=int(value),
                        evidence_span_id=sentence.id,
                    )
                )
                continue

        bal_group = _BAL_GROUP_SAMPLE_RE.search(text)
        if bal_group and "reliability" in text_lower:
            drafts.append(
                _CandidateDraft(
                    raw_text=bal_group.group(0),
                    normalized_value=int(bal_group.group(1)),
                    evidence_span_id=sentence.id,
                )
            )
            continue

        if "all patients" in text_lower and validation_value is not None:
            drafts.append(
                _CandidateDraft(
                    raw_text=text,
                    normalized_value=validation_value,
                    evidence_span_id=sentence.id,
                )
            )

    return _build_field_extraction(
        file_path,
        "retest_sample_n",
        drafts,
        _collect_not_reported_candidates(
            field_aliases=("test-retest", "retest"),
            sentences=sentences,
        ),
    )


def _extract_sample_size_observations(
    file_path: str,
    sentences: tuple[SentenceRecord, ...],
    sample_sizes: ContextFieldExtraction,
    validation_sample_n: ContextFieldExtraction,
    pilot_sample_n: ContextFieldExtraction,
    retest_sample_n: ContextFieldExtraction,
) -> tuple[SampleSizeObservation, ...]:
    drafts: list[_SampleSizeDraft] = []

    for sentence in sentences:
        if _is_reference_sentence(sentence) or _is_background_sentence(sentence):
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
                unit = "observations" if "data point" in match.group(0).lower() else "participants"
                drafts.append(
                    _SampleSizeDraft(
                        role=SampleSizeRole.ANALYZED,
                        raw_text=match.group(0),
                        normalized_value=int(match.group(1)),
                        unit=unit,
                        evidence_span_id=sentence.id,
                    )
                )

        bal_group = _BAL_GROUP_SAMPLE_RE.search(text)
        if bal_group:
            drafts.append(
                _SampleSizeDraft(
                    role=SampleSizeRole.RETEST,
                    raw_text=bal_group.group(0),
                    normalized_value=int(bal_group.group(1)),
                    unit="observations",
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

    for field, role in (
        (validation_sample_n, SampleSizeRole.VALIDATION),
        (pilot_sample_n, SampleSizeRole.PILOT),
        (retest_sample_n, SampleSizeRole.RETEST),
    ):
        for candidate in field.candidates:
            if not isinstance(candidate.normalized_value, int):
                continue
            for evidence_span_id in candidate.evidence_span_ids:
                drafts.append(
                    _SampleSizeDraft(
                        role=role,
                        raw_text=candidate.raw_text,
                        normalized_value=candidate.normalized_value,
                        unit="participants",
                        evidence_span_id=evidence_span_id,
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
    for obs_role, obs_value, obs_unit in sorted(
        grouped,
        key=lambda item: (item[0].value, item[1], item[2] or ""),
    ):
        group = grouped[(obs_role, obs_value, obs_unit)]
        evidence_span_ids = tuple(dict.fromkeys(record.evidence_span_id for record in group))
        raw_text = " || ".join(dict.fromkeys(record.raw_text for record in group))
        observations.append(
            SampleSizeObservation(
                id=_stable_id(
                    "samplerole",
                    file_path,
                    obs_role.value,
                    obs_value,
                    obs_unit or "",
                    *evidence_span_ids,
                ),
                role=obs_role,
                sample_size_raw=raw_text,
                sample_size_normalized=obs_value,
                unit=obs_unit,
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
        if _is_reference_sentence(sentence) or _is_background_sentence(sentence):
            continue
        text = sentence.provenance.raw_text
        text_lower = text.lower()
        if _is_question_like_text(text):
            continue
        if "95% ci" in text_lower or "confidence interval" in text_lower:
            continue

        if (
            "follow-up" not in text_lower
            and "before surgery" not in text_lower
            and not (
                "baseline" in text_lower
                and any(
                    token in text_lower
                    for token in (
                        "after",
                        "visit",
                        "timepoint",
                        "month",
                        "months",
                        "week",
                        "weeks",
                        "year",
                        "years",
                    )
                )
            )
        ):
            continue

        deduplicated = _extract_schedule_tokens(text_lower)
        if len(deduplicated) < 2:
            continue

        drafts.append(
            _CandidateDraft(
                raw_text=text,
                normalized_value=deduplicated,
                evidence_span_id=sentence.id,
            )
        )

    drafts = _prefer_specific_follow_up_schedule(drafts)

    return _build_field_extraction(
        file_path,
        "follow_up_schedule",
        drafts,
        _collect_not_reported_candidates(
            field_aliases=("follow-up", "follow up", "baseline"),
            sentences=sentences,
        ),
    )


def _extract_follow_up_interval(
    file_path: str,
    sentences: tuple[SentenceRecord, ...],
) -> ContextFieldExtraction:
    drafts: list[_CandidateDraft] = []
    range_pattern = re.compile(
        r"\b(\d+)\s*(?:to|-|–)\s*(\d+)\s*(minute|minutes|day|days|week|weeks|month|months|year|years)\b",
        flags=re.IGNORECASE,
    )
    for sentence in sentences:
        if _is_reference_sentence(sentence) or _is_background_sentence(sentence):
            continue
        text = sentence.provenance.raw_text
        text_lower = text.lower()
        if _is_question_like_text(text):
            continue
        if (
            "95% ci" in text_lower
            or "confidence interval" in text_lower
            or re.search(r"\bci\b", text_lower)
        ):
            continue
        if _CITATION_RE.search(text) and any(
            token in text_lower for token in ("previous", "prior", "others", "historical")
        ):
            continue
        if "historical interval" in text_lower:
            continue
        if (
            ("stage 1" in text_lower and "stage 2" in text_lower) or "two stages" in text_lower
        ) and "retest" not in text_lower:
            continue
        if (
            "retest" not in text_lower
            and "interval" not in text_lower
            and "session" not in text_lower
            and "follow-up visit" not in text_lower
        ):
            continue

        range_match = range_pattern.search(text_lower)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2))
            unit = range_match.group(3)
            normalized_unit = _normalize_interval_unit(unit)
            normalized_start = start
            normalized_end = end
            if normalized_unit == "years":
                normalized_unit = "months"
                normalized_start *= 12
                normalized_end *= 12
            drafts.append(
                _CandidateDraft(
                    raw_text=text,
                    normalized_value=(f"{normalized_start} to {normalized_end} {normalized_unit}"),
                    evidence_span_id=sentence.id,
                )
            )
            continue

        match = _FOLLOW_UP_INTERVAL_WORD_RE.search(text_lower)
        if not match:
            continue
        number = _word_or_number_to_int(match.group(1))
        if number is None:
            continue
        unit = match.group(2)
        normalized_unit = _normalize_interval_unit(unit)
        normalized_number = number
        if normalized_unit == "years":
            normalized_unit = "months"
            normalized_number *= 12
        drafts.append(
            _CandidateDraft(
                raw_text=text,
                normalized_value=f"{normalized_number} {normalized_unit}",
                evidence_span_id=sentence.id,
            )
        )

    drafts = _prefer_specific_follow_up_interval(drafts)

    return _build_field_extraction(
        file_path,
        "follow_up_interval",
        drafts,
        _collect_not_reported_candidates(
            field_aliases=("follow-up interval", "test-retest interval", "interval"),
            sentences=sentences,
        ),
    )


def _extract_recruitment_setting(
    file_path: str,
    sentences: tuple[SentenceRecord, ...],
) -> ContextFieldExtraction:
    drafts: list[_CandidateDraft] = []
    investigation_pattern = re.compile(
        r"(?:investigation performed at|performed at)\s+[^.]{0,200}",
        flags=re.IGNORECASE,
    )
    for sentence in sentences:
        if _is_reference_sentence(sentence) or _is_background_sentence(sentence):
            continue
        text = sentence.provenance.raw_text
        text_lower = text.lower()
        heading_tokens = " ".join(sentence.heading_path).lower()
        if any(token in text_lower for token in ("email:", "@", "correspondence", "disclaimer")):
            continue
        if any(token in heading_tokens for token in ("author", "affiliation", "acknowledg")):
            continue
        match = _RECRUITMENT_SETTING_RE.search(text)
        if match:
            value = _normalize_text_value(match.group(0))
            raw = match.group(0)
        else:
            investigation_match = investigation_pattern.search(text)
            if investigation_match:
                value = _normalize_text_value(investigation_match.group(0))
                raw = investigation_match.group(0)
            elif _AURORA_SETTING_RE.search(text) and any(
                token in text_lower
                for token in (
                    "study",
                    "participants",
                    "patients",
                    "recruit",
                    "performed",
                    "investigation",
                )
            ):
                value = _normalize_text_value(text)
                raw = text
            else:
                continue
        drafts.append(
            _CandidateDraft(
                raw_text=raw,
                normalized_value=value,
                evidence_span_id=sentence.id,
            )
        )

    return _build_field_extraction(
        file_path,
        "recruitment_setting",
        drafts,
        _collect_not_reported_candidates(
            field_aliases=("recruited", "enrolled", "single center", "from"),
            sentences=sentences,
        ),
    )


def _extract_measurement_property_partitions(
    file_path: str,
    sentences: tuple[SentenceRecord, ...],
) -> tuple[
    ContextFieldExtraction, ContextFieldExtraction, ContextFieldExtraction, ContextFieldExtraction
]:
    property_needles: tuple[tuple[str, str], ...] = (
        ("content validity", "content_validity"),
        ("structural validity", "structural_validity"),
        ("rasch", "structural_validity"),
        ("irt", "structural_validity"),
        ("item fit", "structural_validity"),
        ("infit", "structural_validity"),
        ("outfit", "structural_validity"),
        ("local dependence", "structural_validity"),
        ("local independence", "structural_validity"),
        ("unidimensionality", "structural_validity"),
        ("dimensionality", "structural_validity"),
        ("residual pca", "structural_validity"),
        ("threshold ordering", "structural_validity"),
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
    not_assessed_values: set[str] = set()

    direct_evidence: list[_CandidateDraft] = []
    background_evidence: list[_CandidateDraft] = []
    interpretability_evidence: list[_CandidateDraft] = []
    not_assessed_evidence: list[_CandidateDraft] = []

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

        if _is_not_assessed_property_sentence(text_lower):
            not_assessed_values.update(found_here)
            not_assessed_evidence.append(
                _CandidateDraft(
                    raw_text=text,
                    normalized_value=tuple(sorted(found_here)),
                    evidence_span_id=sentence.id,
                )
            )
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
    not_assessed_field = _build_property_field(
        file_path=file_path,
        field_name="measurement_properties_not_assessed",
        values=not_assessed_values,
        evidence=not_assessed_evidence,
        not_reported_candidates=[],
    )

    return direct_field, background_field, interpretability_field, not_assessed_field


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


def _prefer_majority_value(drafts: list[_CandidateDraft]) -> list[_CandidateDraft]:
    grouped: dict[str | int | tuple[str, ...] | None, list[_CandidateDraft]] = defaultdict(list)
    for draft in drafts:
        grouped[draft.normalized_value].append(draft)
    if len(grouped) <= 1:
        return drafts

    ranked = sorted(grouped.items(), key=lambda item: (len(item[1]), str(item[0])), reverse=True)
    top_value, top_items = ranked[0]
    second_count = len(ranked[1][1]) if len(ranked) > 1 else 0
    if top_value is not None and len(top_items) >= 2 and len(top_items) > second_count:
        return list(top_items)
    return drafts


def _prefer_specific_study_design(drafts: list[_CandidateDraft]) -> list[_CandidateDraft]:
    if not drafts:
        return drafts

    specificity = {
        "prospective_cross_sectional_validation_development_study": 7,
        "cross_sectional_validation_study": 6,
        "prospective_observational_study": 5,
        "longitudinal_cohort": 5,
        "randomized_controlled_trial": 5,
        "case_control": 4,
        "cross_sectional": 3,
        "cohort": 3,
        "longitudinal": 2,
        "validation_study": 2,
        "prospective": 1,
    }

    top_score = max(specificity.get(str(draft.normalized_value), 0) for draft in drafts)
    filtered = [
        draft for draft in drafts if specificity.get(str(draft.normalized_value), 0) == top_score
    ]
    return filtered or drafts


def _prefer_specific_target_population(drafts: list[_CandidateDraft]) -> list[_CandidateDraft]:
    if not drafts:
        return drafts

    def score(draft: _CandidateDraft) -> int:
        text = draft.raw_text.lower()
        score_value = 0
        if "inclusion criteria" in text or "recruited" in text:
            score_value += 2
        if "transfemoral" in text and "amputation" in text:
            score_value += 2
        if "lower limb amputation" in text or "lower-extremity amputation" in text:
            score_value += 2
        if "osseointegr" in text:
            score_value += 2
        if _is_question_like_text(draft.raw_text):
            score_value -= 4
        return score_value

    return _prefer_highest_scored_drafts(drafts, score, minimum_score=1)


def _extract_schedule_tokens(text_lower: str) -> tuple[str, ...]:
    tokens: list[str] = []

    if "baseline" in text_lower or "before surgery" in text_lower:
        tokens.append("baseline")

    multi_timepoint_pattern = re.compile(
        r"\b((?:\d+\s*,\s*)+\d+\s*(?:,?\s*and\s*\d+)?)\s*"
        r"(month|months|week|weeks|year|years)\b",
        flags=re.IGNORECASE,
    )
    for match in multi_timepoint_pattern.finditer(text_lower):
        values = re.findall(r"\d+", match.group(1))
        unit = _normalize_interval_unit(match.group(2))
        normalized_unit = unit if unit.endswith("s") else f"{unit}s"
        for value in values:
            amount = int(value)
            if normalized_unit == "years":
                amount *= 12
                normalized_unit = "months"
            tokens.append(f"{amount} {normalized_unit}")

    for match in _INTERVAL_RE.finditer(text_lower):
        amount = int(match.group(1))
        unit = _normalize_interval_unit(match.group(2))
        normalized_unit = unit if unit.endswith("s") else f"{unit}s"
        if normalized_unit == "years":
            amount *= 12
            normalized_unit = "months"
        tokens.append(f"{amount} {normalized_unit}")

    return tuple(dict.fromkeys(tokens))


def _prefer_specific_follow_up_schedule(drafts: list[_CandidateDraft]) -> list[_CandidateDraft]:
    if not drafts:
        return drafts

    def score(draft: _CandidateDraft) -> int:
        text = draft.raw_text.lower()
        score_value = 0
        if isinstance(draft.normalized_value, tuple):
            score_value += len(draft.normalized_value)
            if "baseline" in draft.normalized_value:
                score_value += 2
        if "follow-up visit" in text or "regular follow-up visits" in text:
            score_value += 2
        if "participants were asked to complete" in text:
            score_value += 2
        if _is_question_like_text(draft.raw_text):
            score_value -= 3
        if "historical interval" in text:
            score_value -= 3
        return score_value

    return _prefer_highest_scored_drafts(drafts, score, minimum_score=3)


def _prefer_specific_follow_up_interval(drafts: list[_CandidateDraft]) -> list[_CandidateDraft]:
    if not drafts:
        return drafts

    def score(draft: _CandidateDraft) -> int:
        text = draft.raw_text.lower()
        score_value = 0
        if "test-retest" in text or "retest" in text:
            score_value += 3
        if "follow-up visit" in text:
            score_value += 2
        if "interval" in text:
            score_value += 1
        if _is_question_like_text(draft.raw_text):
            score_value -= 3
        if "historical interval" in text:
            score_value -= 3
        if (
            ("stage 1" in text and "stage 2" in text) or "two stages" in text
        ) and "retest" not in text:
            score_value -= 3
        if _CITATION_RE.search(draft.raw_text) and any(
            token in text for token in ("previous", "prior", "others")
        ):
            score_value -= 2
        return score_value

    return _prefer_highest_scored_drafts(drafts, score, minimum_score=1)


def _prefer_highest_scored_drafts(
    drafts: list[_CandidateDraft],
    scorer: Callable[[_CandidateDraft], int],
    *,
    minimum_score: int,
) -> list[_CandidateDraft]:
    if not drafts:
        return drafts

    scored = [(scorer(draft), draft) for draft in drafts]
    top_score = max(score for score, _ in scored)
    if top_score < minimum_score:
        return drafts

    top_drafts = [draft for score, draft in scored if score == top_score]
    return top_drafts or drafts


def _normalize_interval_unit(unit_raw: str) -> str:
    unit = unit_raw.lower()
    return unit if unit.endswith("s") else f"{unit}s"


def _is_question_like_text(text: str) -> bool:
    text_lower = text.lower()
    if "?" in text:
        return True
    if "questions/purposes" in text_lower:
        return True
    return text_lower.startswith(("did ", "what was ", "what functional outcomes"))


def _extract_number_tokens(text: str) -> tuple[_NumberToken, ...]:
    tokens: list[_NumberToken] = []
    for match in re.finditer(r"\b\d+\b", text):
        tokens.append(_NumberToken(raw_text=match.group(0), value=int(match.group(0))))
    for word, value in _NUMBER_WORDS.items():
        if re.search(rf"\b{word}\b", text.lower()):
            tokens.append(_NumberToken(raw_text=word, value=value))
    return tuple(tokens)


def _word_or_number_to_int(raw_value: str) -> int | None:
    normalized = raw_value.strip().lower()
    if normalized.isdigit():
        return int(normalized)
    return _NUMBER_WORDS.get(normalized)


def _first_int_candidate(field: ContextFieldExtraction) -> int | None:
    if field.status is not FieldDetectionStatus.DETECTED:
        return None
    if not field.candidates:
        return None
    value = field.candidates[0].normalized_value
    return value if isinstance(value, int) else None


def _normalize_text_value(raw_value: str) -> str:
    value = re.sub(r"\s+", " ", raw_value).strip(" .;:,\t")
    return value


def _normalize_instrument_name_candidate(raw_value: str) -> str:
    value = _normalize_text_value(raw_value).strip("()")
    parenthetical_match = _PARENTHETICAL_ACRONYM_RE.search(value)
    if parenthetical_match:
        # Favor explicit short-form labels in parentheses for stable grouping.
        value = _normalize_text_value(parenthetical_match.group(1))
    value_lower = value.lower()

    if not value:
        return ""
    if _SIGAM_FULL_RE.search(value) or _SIGAM_ABBR_RE.search(value):
        return "SIGAM"
    if _LCI5_FULL_RE.search(value) or _LCI5_ABBR_RE.search(value):
        return "LCI-5"
    if _HOUGHTON_RE.search(value):
        return "Houghton"
    if _ABC_FULL_RE.search(value) or _ABC_ABBR_RE.search(value):
        return "ABC"
    if _GPS_FULL_RE.search(value) or _GPS_ABBR_RE.search(value):
        return "GPS"
    if _TWO_MWT_FULL_RE.search(value) or _TWO_MWT_ABBR_RE.search(value):
        return "2-MWT"
    if _TUG_FULL_RE.search(value) or _TUG_ABBR_RE.search(value):
        return "TUG"
    if _COLD_TUG_FULL_RE.search(value) or _COLD_TUG_ABBR_RE.search(value):
        return "COLD-TUG"
    if _SIX_MWT_FULL_RE.search(value) or _SIX_MWT_ABBR_RE.search(value):
        return "6-MWT"
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


def _split_outcome_or_instrument_list(raw_value: str) -> tuple[str, ...]:
    text = re.sub(r"\([^)]*\)", "", raw_value)
    text = text.replace(" and ", ",")
    text = text.replace(" or ", ",")
    items = [item.strip(" :;,.") for item in text.split(",")]
    filtered = [item for item in items if item]
    return tuple(dict.fromkeys(filtered))


def _normalize_version(raw_value: str) -> str:
    value = raw_value.strip().lower().removeprefix("version ")
    return value.removeprefix("v")


def _classify_instrument_type(
    *,
    normalized_name: str,
    sentences: tuple[SentenceRecord, ...],
) -> tuple[InstrumentType, str, tuple[StableId, ...]]:
    name = normalized_name.strip()
    name_lower = name.lower()
    evidence_sentences = [
        sentence
        for sentence in sentences
        if re.search(rf"\b{re.escape(name_lower)}\b", sentence.provenance.raw_text.lower())
    ]
    evidence_span_ids = tuple(dict.fromkeys(sentence.id for sentence in evidence_sentences))
    name_pattern = re.compile(rf"\b{re.escape(name_lower)}\b")

    prom_name_pattern = re.compile(
        r"(questionnaire|scale|survey|inventory|patient-?reported|domain\s+score)"
    )
    prom_context_pattern = re.compile(
        r"(questionnaire|scale|translated|translation|cross-?cultur|adapt(?:ed|ation)|"
        r"psychometric|internal consistency|cronbach|kr-?20|version|"
        r"rasch|irt|item\s+fit|infit|outfit|local\s+independence|local\s+dependence|"
        r"unidimensional(?:ity)?|dimensionality|residual\s+pca|threshold\s+ordering)",
        re.IGNORECASE,
    )
    performance_name_pattern = re.compile(
        r"(timed|walk|test|up-?\s*and-?\s*go|\btug\b|\bmwt\b|donning)"
    )
    performance_context_pattern = re.compile(
        r"(timed|walk\s+test|up-?\s*and-?\s*go|seconds?|performance-?based|"
        r"functional\s+test|donning)",
        re.IGNORECASE,
    )
    pbom_context_pattern = re.compile(
        r"(performance-?based\s+outcome|functional\s+test|mobility\s+test|mobility\s+predictor)",
        re.IGNORECASE,
    )

    prom_signal_score = 0
    performance_signal_score = 0
    pbom_signal_score = 0

    if prom_name_pattern.search(name_lower):
        prom_signal_score += 3
    if performance_name_pattern.search(name_lower):
        performance_signal_score += 3

    for sentence in evidence_sentences:
        text_lower = sentence.provenance.raw_text.lower()
        if prom_context_pattern.search(text_lower):
            prom_signal_score += 1
        if performance_context_pattern.search(text_lower):
            performance_signal_score += 1
        if pbom_context_pattern.search(text_lower):
            pbom_signal_score += 1

        for match in name_pattern.finditer(text_lower):
            window_start = max(0, match.start() - 90)
            window_end = min(len(text_lower), match.end() + 90)
            window_text = text_lower[window_start:window_end]
            if prom_context_pattern.search(window_text):
                prom_signal_score += 2
            if performance_context_pattern.search(window_text):
                performance_signal_score += 2
            if pbom_context_pattern.search(window_text):
                pbom_signal_score += 2

    if prom_signal_score >= 3 and prom_signal_score >= performance_signal_score:
        return (
            InstrumentType.PROM,
            "Classified as PROM from questionnaire/scale/translation psychometric context.",
            evidence_span_ids,
        )
    if performance_signal_score >= 3 and performance_signal_score > prom_signal_score:
        return (
            InstrumentType.PERFORMANCE_TEST,
            "Classified as performance test from timed/functional local context.",
            evidence_span_ids,
        )
    if pbom_signal_score >= 2 and pbom_signal_score >= max(
        prom_signal_score,
        performance_signal_score,
    ):
        return (
            InstrumentType.PBOM,
            "Classified as PBOM from performance-based outcome terminology.",
            evidence_span_ids,
        )

    if prom_signal_score > 0 and performance_signal_score > 0:
        return (
            InstrumentType.MIXED_OR_UNKNOWN,
            "Both questionnaire-like and performance-like cues were present; "
            "reviewer confirmation is required.",
            evidence_span_ids,
        )

    return (
        InstrumentType.MIXED_OR_UNKNOWN,
        "No deterministic instrument-type signal was strong enough.",
        evidence_span_ids,
    )


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


def _infer_instrument_roles(
    *,
    sentences: tuple[SentenceRecord, ...],
    study_intent: StudyIntent,
    normalized_instrument_names: tuple[tuple[StableId, str], ...],
) -> dict[StableId, tuple[InstrumentContextRole, str, tuple[StableId, ...]]]:
    by_name: dict[str, StableId] = {
        normalized_name: instrument_id
        for instrument_id, normalized_name in normalized_instrument_names
    }
    by_id: dict[StableId, str] = {
        instrument_id: normalized_name
        for instrument_id, normalized_name in normalized_instrument_names
    }
    target_scores: dict[StableId, int] = {
        instrument_id: 0 for instrument_id, _ in normalized_instrument_names
    }
    comparator_scores: dict[StableId, int] = {
        instrument_id: 0 for instrument_id, _ in normalized_instrument_names
    }
    outcome_scores: dict[StableId, int] = {
        instrument_id: 0 for instrument_id, _ in normalized_instrument_names
    }
    anchor_scores: dict[StableId, int] = {
        instrument_id: 0 for instrument_id, _ in normalized_instrument_names
    }
    target_evidence: dict[StableId, list[StableId]] = {
        instrument_id: [] for instrument_id, _ in normalized_instrument_names
    }
    comparator_evidence: dict[StableId, list[StableId]] = {
        instrument_id: [] for instrument_id, _ in normalized_instrument_names
    }
    outcome_evidence: dict[StableId, list[StableId]] = {
        instrument_id: [] for instrument_id, _ in normalized_instrument_names
    }

    study_intent_re = re.compile(
        r"\b(?:aim|objective|purpose)\b[^.]{0,220}"
        r"\b(?:develop|validate|validation|adapt|psychometric)\b",
        re.IGNORECASE,
    )
    comparator_relation_re = re.compile(
        r"\b(?:compared?\s+with|comparison(?:s)?\s+with|by comparing|"
        r"correlat(?:ed|ion(?:s)?)\s+(?:between|with)|association\s+(?:between|with))\b",
        re.IGNORECASE,
    )
    appraisal_re = re.compile(
        (
            r"\b(?:reliability|validity|internal consistency|measurement error|"
            r"responsiveness|psychometric|rasch|irt)\b"
        ),
        re.IGNORECASE,
    )
    outcome_re = re.compile(
        r"\b(?:patient-reported outcome|outcome measure|baseline|follow-up|"
        r"improv(?:e|ed|ement)|change|mcid|mic)\b",
        re.IGNORECASE,
    )
    anchor_re = re.compile(
        r"\b(?:anchor-based|anchor based|mcid|mic)\b[^.]{0,120}\b(?:global score|anchor)\b",
        re.IGNORECASE,
    )
    interpretability_outcome_re = re.compile(
        r"\b(?:mcid|mic|mid|anchor-?based|distribution-?based)\b",
        re.IGNORECASE,
    )
    interpretability_scores: dict[StableId, int] = {
        instrument_id: 0 for instrument_id, _ in normalized_instrument_names
    }
    joint_psychometric_scores: dict[StableId, int] = {
        instrument_id: 0 for instrument_id, _ in normalized_instrument_names
    }

    for sentence in sentences:
        if _is_reference_sentence(sentence) or _is_background_sentence(sentence):
            continue
        text = sentence.provenance.raw_text
        text_lower = text.lower()
        mentioned_ids = [
            instrument_id
            for normalized_name, instrument_id in by_name.items()
            if _instrument_text_position(normalized_name, text_lower) >= 0
        ]
        if not mentioned_ids:
            continue

        if "title" in " ".join(sentence.heading_path).lower():
            for instrument_id in mentioned_ids:
                target_scores[instrument_id] += 3
                target_evidence[instrument_id].append(sentence.id)

        for pattern in _TARGET_PRIORITY_PATTERNS:
            if pattern.search(text):
                for instrument_id in mentioned_ids:
                    target_scores[instrument_id] += 3
                    target_evidence[instrument_id].append(sentence.id)
                break

        if study_intent_re.search(text) and appraisal_re.search(text):
            comparator_match = _COMPARATOR_CONTEXT_RE.search(text) or comparator_relation_re.search(
                text
            )
            if comparator_match:
                comparator_anchor = comparator_match.start()
                ordered_mentions = sorted(
                    (
                        (_instrument_text_position(normalized_name, text_lower), instrument_id)
                        for normalized_name, instrument_id in by_name.items()
                        if _instrument_text_position(normalized_name, text_lower) >= 0
                    ),
                    key=lambda item: item[0],
                )
                for position, instrument_id in ordered_mentions:
                    if position < comparator_anchor:
                        target_scores[instrument_id] += 4
                        target_evidence[instrument_id].append(sentence.id)
                        if len(mentioned_ids) >= 2:
                            joint_psychometric_scores[instrument_id] += 1
                    else:
                        comparator_scores[instrument_id] += 1
                        comparator_evidence[instrument_id].append(sentence.id)
            else:
                for instrument_id in mentioned_ids:
                    target_scores[instrument_id] += 4
                    target_evidence[instrument_id].append(sentence.id)
                    if len(mentioned_ids) >= 2:
                        joint_psychometric_scores[instrument_id] += 1

        if outcome_re.search(text):
            for instrument_id in mentioned_ids:
                outcome_scores[instrument_id] += 2
                outcome_evidence[instrument_id].append(sentence.id)

        if "patient-reported outcome" in text_lower and len(mentioned_ids) >= 2:
            for instrument_id in mentioned_ids:
                outcome_scores[instrument_id] += 2
                outcome_evidence[instrument_id].append(sentence.id)

        if anchor_re.search(text):
            for instrument_id in mentioned_ids:
                anchor_scores[instrument_id] += 3
                outcome_scores[instrument_id] += 1
                outcome_evidence[instrument_id].append(sentence.id)
        if interpretability_outcome_re.search(text):
            for instrument_id in mentioned_ids:
                interpretability_scores[instrument_id] += 2
                outcome_scores[instrument_id] += 1
                outcome_evidence[instrument_id].append(sentence.id)

        comparator_match = _COMPARATOR_CONTEXT_RE.search(text) or comparator_relation_re.search(
            text
        )
        if comparator_match:
            comparator_anchor = comparator_match.start()
            ordered_mentions = sorted(
                (
                    (_instrument_text_position(normalized_name, text_lower), instrument_id)
                    for normalized_name, instrument_id in by_name.items()
                    if _instrument_text_position(normalized_name, text_lower) >= 0
                ),
                key=lambda item: item[0],
            )
            if len(ordered_mentions) >= 2:
                lead_id = ordered_mentions[0][1]
                lead_position = ordered_mentions[0][0]
                if lead_position < comparator_anchor:
                    target_scores[lead_id] += 2
                    target_evidence[lead_id].append(sentence.id)
                for _, instrument_id in ordered_mentions[1:]:
                    comparator_scores[instrument_id] += 3
                    comparator_evidence[instrument_id].append(sentence.id)
            else:
                for instrument_id in mentioned_ids:
                    comparator_scores[instrument_id] += 1
                    comparator_evidence[instrument_id].append(sentence.id)

        if "by comparing" in text_lower and " to " in text_lower:
            lead = text_lower.split(" to ", 1)[0]
            for normalized_name, instrument_id in by_name.items():
                if normalized_name.lower() in lead:
                    target_scores[instrument_id] += 4
                    target_evidence[instrument_id].append(sentence.id)
                elif normalized_name.lower() in text_lower:
                    comparator_scores[instrument_id] += 3
                    comparator_evidence[instrument_id].append(sentence.id)

        if study_intent_re.search(text) and len(mentioned_ids) > 1:
            first_mention_positions = sorted(
                (
                    (_instrument_text_position(normalized_name, text_lower), instrument_id)
                    for normalized_name, instrument_id in by_name.items()
                    if _instrument_text_position(normalized_name, text_lower) >= 0
                ),
                key=lambda item: item[0],
            )
            if first_mention_positions:
                lead_id = first_mention_positions[0][1]
                target_scores[lead_id] += 2
                target_evidence[lead_id].append(sentence.id)
                for _, instrument_id in first_mention_positions[1:]:
                    comparator_scores[instrument_id] += 1
                    comparator_evidence[instrument_id].append(sentence.id)

    assignments: dict[StableId, tuple[InstrumentContextRole, str, tuple[StableId, ...]]] = {}
    selected_target_id: StableId | None = None

    if study_intent is StudyIntent.LONGITUDINAL_OUTCOME:
        ranked_outcome = sorted(
            outcome_scores.items(),
            key=lambda item: (
                item[1],
                anchor_scores[item[0]],
                target_scores[item[0]],
                str(item[0]),
            ),
            reverse=True,
        )
        max_outcome_score = ranked_outcome[0][1] if ranked_outcome else 0
        if max_outcome_score <= 0:
            return assignments
        co_primary_ids = {
            instrument_id
            for instrument_id, score in ranked_outcome
            if score >= 3 and score >= max_outcome_score - 1
        }
        co_primary_ids.update(
            instrument_id for instrument_id, score in anchor_scores.items() if score > 0
        )
        if len(co_primary_ids) >= 2:
            for instrument_id in co_primary_ids:
                evidence_ids = tuple(dict.fromkeys(outcome_evidence[instrument_id]))
                assignments[instrument_id] = (
                    InstrumentContextRole.CO_PRIMARY_OUTCOME_INSTRUMENT,
                    (
                        "Classified as co-primary outcome instrument from longitudinal "
                        "outcome and/or anchor evidence."
                    ),
                    evidence_ids,
                )
        else:
            lead_instrument_id = ranked_outcome[0][0]
            assignments[lead_instrument_id] = (
                InstrumentContextRole.TARGET_UNDER_APPRAISAL,
                "Lead longitudinal outcome instrument based on strongest direct outcome signal.",
                tuple(dict.fromkeys(outcome_evidence[lead_instrument_id])),
            )

        for instrument_id, _ in normalized_instrument_names:
            if instrument_id in assignments:
                continue
            comparator_evidence_ids = tuple(dict.fromkeys(comparator_evidence[instrument_id]))
            if comparator_scores[instrument_id] > outcome_scores[instrument_id]:
                assignments[instrument_id] = (
                    InstrumentContextRole.COMPARATOR_ONLY,
                    "Detected as comparator-only context in longitudinal outcome study.",
                    comparator_evidence_ids,
                )
                continue
            outcome_evidence_ids = tuple(dict.fromkeys(outcome_evidence[instrument_id]))
            if outcome_scores[instrument_id] > 0:
                assignments[instrument_id] = (
                    InstrumentContextRole.SECONDARY_OUTCOME_INSTRUMENT,
                    "Classified as secondary outcome instrument from longitudinal reporting.",
                    outcome_evidence_ids,
                )
            else:
                assignments[instrument_id] = (
                    InstrumentContextRole.BACKGROUND_ONLY,
                    "Mentioned without direct outcome-appraisal evidence in this study.",
                    outcome_evidence_ids or comparator_evidence_ids,
                )
        return assignments

    if study_intent is StudyIntent.MIXED:
        outcome_positive = [
            instrument_id for instrument_id, score in outcome_scores.items() if score > 0
        ]
        strongest_target_signal = max(target_scores.values()) if target_scores else 0
        interpretability_positive = [
            instrument_id
            for instrument_id, score in interpretability_scores.items()
            if score > 0 and outcome_scores[instrument_id] > 0
        ]
        if len(interpretability_positive) >= 2:
            for instrument_id in interpretability_positive:
                assignments[instrument_id] = (
                    InstrumentContextRole.CO_PRIMARY_OUTCOME_INSTRUMENT,
                    (
                        "Interpretability-focused mixed study with multiple co-studied "
                        "outcomes; retained as co-primary outcome instrument."
                    ),
                    tuple(dict.fromkeys(outcome_evidence[instrument_id])),
                )

            for instrument_id, _ in normalized_instrument_names:
                if instrument_id in assignments:
                    continue
                comparator_evidence_ids = tuple(dict.fromkeys(comparator_evidence[instrument_id]))
                outcome_evidence_ids = tuple(dict.fromkeys(outcome_evidence[instrument_id]))
                if outcome_scores[instrument_id] > 0:
                    assignments[instrument_id] = (
                        InstrumentContextRole.SECONDARY_OUTCOME_INSTRUMENT,
                        (
                            "Mentioned as an additional studied outcome in an "
                            "interpretability-focused mixed study."
                        ),
                        outcome_evidence_ids,
                    )
                    continue
                if comparator_scores[instrument_id] > 0:
                    assignments[instrument_id] = (
                        InstrumentContextRole.COMPARATOR_ONLY,
                        "Detected primarily in comparator context relative to co-studied outcomes.",
                        comparator_evidence_ids,
                    )
                    continue
                assignments[instrument_id] = (
                    InstrumentContextRole.BACKGROUND_ONLY,
                    "Mentioned without direct co-outcome evidence in this mixed study context.",
                    outcome_evidence_ids or comparator_evidence_ids,
                )
            return assignments

        if len(outcome_positive) >= 2 and strongest_target_signal <= 2:
            ranked_outcome = sorted(
                outcome_scores.items(),
                key=lambda item: (
                    item[1],
                    anchor_scores[item[0]],
                    target_scores[item[0]],
                    str(item[0]),
                ),
                reverse=True,
            )
            max_outcome = ranked_outcome[0][1] if ranked_outcome else 0
            co_primary_ids = {
                instrument_id
                for instrument_id, score in ranked_outcome
                if score > 0 and score >= max(2, max_outcome - 1)
            }

            for instrument_id in co_primary_ids:
                assignments[instrument_id] = (
                    InstrumentContextRole.CO_PRIMARY_OUTCOME_INSTRUMENT,
                    (
                        "Multiple direct outcome signals detected; retained as co-primary "
                        "outcome instrument."
                    ),
                    tuple(dict.fromkeys(outcome_evidence[instrument_id])),
                )

            for instrument_id, _ in normalized_instrument_names:
                if instrument_id in assignments:
                    continue
                comparator_evidence_ids = tuple(dict.fromkeys(comparator_evidence[instrument_id]))
                outcome_evidence_ids = tuple(dict.fromkeys(outcome_evidence[instrument_id]))
                if comparator_scores[instrument_id] > outcome_scores[instrument_id]:
                    assignments[instrument_id] = (
                        InstrumentContextRole.COMPARATOR_ONLY,
                        "Detected primarily in comparator context relative to co-primary outcomes.",
                        comparator_evidence_ids,
                    )
                    continue
                if outcome_scores[instrument_id] > 0:
                    assignments[instrument_id] = (
                        InstrumentContextRole.SECONDARY_OUTCOME_INSTRUMENT,
                        "Detected as secondary outcome in a mixed, outcome-oriented study context.",
                        outcome_evidence_ids,
                    )
                else:
                    assignments[instrument_id] = (
                        InstrumentContextRole.BACKGROUND_ONLY,
                        (
                            "Mentioned without direct outcome-appraisal evidence in this "
                            "mixed study context."
                        ),
                        outcome_evidence_ids or comparator_evidence_ids,
                    )
            return assignments

    if study_intent is StudyIntent.PSYCHOMETRIC_VALIDATION:
        co_primary_ids = {
            instrument_id
            for instrument_id, score in target_scores.items()
            if score > 0 and joint_psychometric_scores[instrument_id] > 0
        }
        if len(co_primary_ids) >= 2:
            for instrument_id in co_primary_ids:
                evidence_ids = tuple(
                    dict.fromkeys(target_evidence[instrument_id] + outcome_evidence[instrument_id])
                )
                assignments[instrument_id] = (
                    InstrumentContextRole.CO_PRIMARY_OUTCOME_INSTRUMENT,
                    (
                        "Multiple instruments were directly appraised for psychometric "
                        "properties in the same study context."
                    ),
                    evidence_ids,
                )

            for instrument_id, _ in normalized_instrument_names:
                if instrument_id in assignments:
                    continue
                comparator_evidence_ids = tuple(dict.fromkeys(comparator_evidence[instrument_id]))
                target_evidence_ids = tuple(dict.fromkeys(target_evidence[instrument_id]))
                if comparator_scores[instrument_id] > target_scores[instrument_id]:
                    assignments[instrument_id] = (
                        InstrumentContextRole.COMPARATOR_ONLY,
                        (
                            "Detected primarily in comparator context relative to "
                            "co-appraised psychometric targets."
                        ),
                        comparator_evidence_ids,
                    )
                else:
                    assignments[instrument_id] = (
                        InstrumentContextRole.ADDITIONAL,
                        "Retained as an additional instrument mention without role dominance.",
                        target_evidence_ids or comparator_evidence_ids,
                    )
            return assignments

        ranked = sorted(
            target_scores.items(),
            key=lambda item: (
                item[1] - comparator_scores[item[0]],
                item[1],
                str(item[0]),
            ),
            reverse=True,
        )
    else:
        ranked = sorted(
            target_scores.items(),
            key=lambda item: (item[1] - comparator_scores[item[0]], item[1], str(item[0])),
            reverse=True,
        )
    if ranked and ranked[0][1] > 0:
        selected_target_id = ranked[0][0]
        evidence_ids = tuple(dict.fromkeys(target_evidence[selected_target_id]))
        assignments[selected_target_id] = (
            InstrumentContextRole.TARGET_UNDER_APPRAISAL,
            (
                "Highest target-signal instrument from study-intent and appraisal-context "
                "sentences."
            ),
            evidence_ids,
        )

    for instrument_id, _ in normalized_instrument_names:
        if instrument_id in assignments:
            continue
        comparator_evidence_ids = tuple(dict.fromkeys(comparator_evidence[instrument_id]))
        target_evidence_ids = tuple(dict.fromkeys(target_evidence[instrument_id]))
        outcome_evidence_ids = tuple(dict.fromkeys(outcome_evidence[instrument_id]))
        if (
            study_intent is StudyIntent.PSYCHOMETRIC_VALIDATION
            and selected_target_id is not None
            and instrument_id != selected_target_id
            and _is_same_instrument_family(
                by_id[instrument_id],
                by_id[selected_target_id],
            )
        ):
            assignments[instrument_id] = (
                InstrumentContextRole.CO_PRIMARY_OUTCOME_INSTRUMENT,
                (
                    "Instrument variant shares the same family stem as the selected "
                    "psychometric target; retained as co-primary under appraisal."
                ),
                target_evidence_ids or outcome_evidence_ids,
            )
            continue
        if (
            study_intent is StudyIntent.PSYCHOMETRIC_VALIDATION
            and selected_target_id is not None
            and instrument_id != selected_target_id
            and comparator_scores[instrument_id] > 0
        ):
            assignments[instrument_id] = (
                InstrumentContextRole.COMPARATOR_ONLY,
                "Validation-study comparator retained as comparator-only support instrument.",
                comparator_evidence_ids,
            )
            continue
        if comparator_scores[instrument_id] > 0 and (
            target_scores[instrument_id] == 0
            or comparator_scores[instrument_id] >= target_scores[instrument_id]
            or (len(comparator_evidence_ids) >= 2 and target_scores[instrument_id] <= 3)
        ):
            assignments[instrument_id] = (
                InstrumentContextRole.COMPARATOR_ONLY,
                "Detected primarily in comparator/correlation context relative to target.",
                comparator_evidence_ids,
            )
        else:
            assignments[instrument_id] = (
                InstrumentContextRole.ADDITIONAL,
                "Retained as an additional instrument mention without role dominance.",
                target_evidence_ids or comparator_evidence_ids,
            )

    return assignments


def _classify_study_intent(
    *,
    sentences: tuple[SentenceRecord, ...],
) -> tuple[StudyIntent, str, tuple[StableId, ...]]:
    psychometric_re = re.compile(
        r"\b(?:validate|validation|psychometric|cross-?cultural|translated|"
        r"internal consistency|test-?retest|construct validity|criterion validity)\b",
        re.IGNORECASE,
    )
    longitudinal_outcome_re = re.compile(
        r"\b(?:baseline|follow-up|complication|therapeutic study|intervention|longitudinal)\b",
        re.IGNORECASE,
    )
    interpretability_re = re.compile(
        r"\b(?:mcid|mic|mid|min(?:imum|imal)\s+clinically\s+important\s+difference|"
        r"anchor-?based|distribution-?based)\b",
        re.IGNORECASE,
    )
    psychometric_aim_re = re.compile(
        r"\b(?:aim|objective|purpose)\b[^.]{0,260}"
        r"\b(?:develop|development|validate|validation|psychometric|"
        r"reliability|validity|cross-?cultural|translate|adapt)\b",
        re.IGNORECASE,
    )
    validation_design_re = re.compile(
        r"\b(?:prospective|cross-?sectional)\b[^.]{0,180}\b(?:validation|development)\b",
        re.IGNORECASE,
    )
    outcome_aim_re = re.compile(
        r"\b(?:aim|objective|purpose)\b[^.]{0,260}"
        r"\b(?:outcome|improv(?:e|ed|ement)|complication|follow-up|baseline|"
        r"therapeutic|intervention)\b",
        re.IGNORECASE,
    )
    psychometric_score = 0
    outcome_score = 0
    interpretability_score = 0
    psychometric_evidence: list[StableId] = []
    outcome_evidence: list[StableId] = []
    interpretability_evidence: list[StableId] = []

    for sentence in sentences:
        if _is_reference_sentence(sentence) or _is_background_sentence(sentence):
            continue
        text = sentence.provenance.raw_text
        if psychometric_re.search(text):
            psychometric_score += 1
            psychometric_evidence.append(sentence.id)
        if psychometric_aim_re.search(text) or validation_design_re.search(text):
            psychometric_score += 3
            psychometric_evidence.append(sentence.id)
        if longitudinal_outcome_re.search(text):
            outcome_score += 1
            outcome_evidence.append(sentence.id)
        if outcome_aim_re.search(text):
            outcome_score += 3
            outcome_evidence.append(sentence.id)
        if interpretability_re.search(text):
            interpretability_score += 1
            interpretability_evidence.append(sentence.id)

    if psychometric_score >= 6 and psychometric_score >= outcome_score + 1:
        return (
            StudyIntent.PSYCHOMETRIC_VALIDATION,
            "Psychometric-validation aims and design language dominated outcome language.",
            tuple(dict.fromkeys(psychometric_evidence)),
        )

    if outcome_score >= 6 and outcome_score >= psychometric_score + 2:
        return (
            StudyIntent.LONGITUDINAL_OUTCOME,
            "Longitudinal outcome signals dominated psychometric-validation signals.",
            tuple(dict.fromkeys(outcome_evidence)),
        )
    if psychometric_score >= 4 and psychometric_score >= outcome_score + 2:
        return (
            StudyIntent.PSYCHOMETRIC_VALIDATION,
            "Psychometric-validation signals dominated longitudinal outcome signals.",
            tuple(dict.fromkeys(psychometric_evidence)),
        )
    if interpretability_score > 0 and outcome_score < 6:
        return (
            StudyIntent.MIXED,
            (
                "Interpretability-focused (MIC/MCID) signals were present without clear "
                "longitudinal dominance."
            ),
            tuple(
                dict.fromkeys(interpretability_evidence + outcome_evidence + psychometric_evidence)
            ),
        )
    return (
        StudyIntent.MIXED,
        "Both psychometric-validation and longitudinal-outcome signals were present.",
        tuple(dict.fromkeys(psychometric_evidence + outcome_evidence)),
    )


def _is_reference_sentence(sentence: SentenceRecord) -> bool:
    heading_tokens = " ".join(sentence.heading_path).lower()
    return "references" in heading_tokens or "acknowledg" in heading_tokens


def _is_keyword_sentence(sentence: SentenceRecord) -> bool:
    heading_tokens = " ".join(sentence.heading_path).lower()
    text_lower = sentence.provenance.raw_text.lower()
    return "keyword" in heading_tokens or text_lower.startswith("keywords:")


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


def _is_not_assessed_property_sentence(text_lower: str) -> bool:
    return any(
        token in text_lower
        for token in (
            "not assessed",
            "were not assessed",
            "not evaluated",
            "could not be performed",
            "impossible to verify",
            "lack of a gold standard",
            "future studies",
        )
    )


def _is_external_comparison_sentence(text_lower: str) -> bool:
    return (
        "e.g." in text_lower
        and "n =" in text_lower
        and any(token in text_lower for token in ("french", "turkish", "dutch"))
    )


def _instrument_text_position(normalized_name: str, text_lower: str) -> int:
    needle = normalized_name.lower()
    direct_match = re.search(
        rf"(?<![A-Za-z0-9-]){re.escape(needle)}(?![A-Za-z0-9-])",
        text_lower,
    )
    if direct_match:
        return direct_match.start()

    if normalized_name == "2-MWT":
        full = _TWO_MWT_FULL_RE.search(text_lower)
        if full:
            return full.start()
        short = _TWO_MWT_ABBR_RE.search(text_lower)
        if short:
            return short.start()
        return -1

    if normalized_name == "GPS":
        full = _GPS_FULL_RE.search(text_lower)
        if full:
            return full.start()
        short = _GPS_ABBR_RE.search(text_lower)
        if short:
            return short.start()
        return -1

    if normalized_name == "6-MWT":
        full = _SIX_MWT_FULL_RE.search(text_lower)
        if full:
            return full.start()
        short = _SIX_MWT_ABBR_RE.search(text_lower)
        if short:
            return short.start()
        return -1

    return -1


def _is_same_instrument_family(first_name: str, second_name: str) -> bool:
    first = re.sub(r"[^A-Za-z0-9]", "", first_name).upper()
    second = re.sub(r"[^A-Za-z0-9]", "", second_name).upper()
    if not first or not second or first == second:
        return first == second and bool(first)

    shorter, longer = sorted((first, second), key=len)
    if len(shorter) < 3:
        return False
    if longer.startswith(shorter) and len(longer) - len(shorter) <= 6:
        return True

    common_prefix = len(os.path.commonprefix((first, second)))
    if common_prefix < 3:
        return False
    return len(first) - common_prefix <= 6 and len(second) - common_prefix <= 6


def _is_false_instrument_candidate(value: str, sentence: SentenceRecord) -> bool:
    value_lower = value.lower()
    sentence_lower = sentence.provenance.raw_text.lower()

    if _is_reference_sentence(sentence):
        return True
    if _is_keyword_sentence(sentence):
        return True

    generic_non_instrument_tokens = (
        "implant",
        "device",
        "system",
        "calculator",
        "hospital",
        "medical center",
        "institutional review board",
        "ethical review board",
        "fda",
        "protocol",
        "software",
        "language",
        "translation",
        "figure",
        "table",
    )
    statistic_like_tokens = {
        "kr-20",
        "cronbach",
        "alpha",
        "icc",
        "kappa",
        "cfi",
        "tli",
        "rmsea",
        "srmr",
        "sem",
        "sdc",
        "loa",
        "mic",
        "mcid",
        "auc",
    }
    if any(token in value_lower for token in generic_non_instrument_tokens):
        return True
    if value_lower in statistic_like_tokens:
        return True
    if re.fullmatch(r"(?:cm|mm|m|sec|s|kg|yrs?|years?)", value_lower):
        return True
    if re.search(r"\b(?:email|copyright|disclaimer)\b", sentence_lower):
        return True
    if any(
        token in value_lower
        for token in (
            "participants",
            "participant",
            "collected",
            "recruited",
            "underwent",
            "follow-up visit",
            "for analysis",
        )
    ):
        return True
    if re.search(
        r"\b(?:baseline|follow-?up|month|months|year|years|stage|visit|surgery)\b",
        value_lower,
    ) and not any(
        token in value_lower
        for token in (
            "questionnaire",
            "scale",
            "instrument",
            "measure",
            "test",
            "index",
            "velocity",
            "walk",
        )
    ):
        return True
    if len(value.split()) > 8 and not any(
        token in value_lower
        for token in (
            "questionnaire",
            "scale",
            "instrument",
            "measure",
            "test",
            "index",
            "velocity",
            "score",
        )
    ):
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
