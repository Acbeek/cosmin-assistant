"""Deterministic candidate statistic extraction without threshold interpretation."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from cosmin_assistant.extract.markdown_parser import parse_markdown_file
from cosmin_assistant.extract.spans import ParsedMarkdownDocument, SentenceRecord
from cosmin_assistant.extract.statistics_models import (
    ArticleStatisticsExtractionResult,
    EvidenceMethodLabel,
    EvidenceSourceType,
    MeasurementPropertyRoute,
    ResponsivenessHypothesisStatus,
    StatisticCandidate,
    StatisticType,
)
from cosmin_assistant.models.base import StableId

_DECIMAL = r"-?(?:\d+(?:\.\d+)?|\.\d+)"

_SINGLE_VALUE_PATTERNS: tuple[tuple[StatisticType, re.Pattern[str]], ...] = (
    (
        StatisticType.CRONBACH_ALPHA,
        re.compile(rf"(?:cronbach(?:'s)?\s*alpha|α)\s*(?:=|:)?\s*({_DECIMAL})", re.IGNORECASE),
    ),
    (
        StatisticType.ICC,
        re.compile(rf"\bICC(?:\s*\([^)]+\))?\s*(?:=|:)?\s*({_DECIMAL})", re.IGNORECASE),
    ),
    (
        StatisticType.WEIGHTED_KAPPA,
        re.compile(rf"(?:weighted\s*kappa|κw)\s*(?:=|:)?\s*({_DECIMAL})", re.IGNORECASE),
    ),
    (
        StatisticType.SEM,
        re.compile(rf"\bSEM\b\s*(?:=|:)?\s*({_DECIMAL})", re.IGNORECASE),
    ),
    (
        StatisticType.SDC,
        re.compile(rf"\bSDC\b\s*(?:=|:)?\s*({_DECIMAL})", re.IGNORECASE),
    ),
    (
        StatisticType.MIC,
        re.compile(
            rf"\b(?:MIC|MCID|MID)\b[^\d-]{{0,40}}"
            rf"(?:=|:|to\s+be|was|is|of|calculated\s+as)\s*({_DECIMAL})",
            re.IGNORECASE,
        ),
    ),
    (
        StatisticType.CFI,
        re.compile(rf"\bCFI\b\s*(?:=|:)?\s*({_DECIMAL})", re.IGNORECASE),
    ),
    (
        StatisticType.TLI,
        re.compile(rf"\bTLI\b\s*(?:=|:)?\s*({_DECIMAL})", re.IGNORECASE),
    ),
    (
        StatisticType.RMSEA,
        re.compile(rf"\bRMSEA\b\s*(?:=|:)?\s*({_DECIMAL})", re.IGNORECASE),
    ),
    (
        StatisticType.SRMR,
        re.compile(rf"\bSRMR\b\s*(?:=|:)?\s*({_DECIMAL})", re.IGNORECASE),
    ),
    (
        StatisticType.AUC,
        re.compile(rf"\b(?:AUC|ROC\s*AUC)\b\s*(?:=|:)?\s*({_DECIMAL})", re.IGNORECASE),
    ),
    (
        StatisticType.CORRELATION,
        re.compile(rf"\b(?:r|rho)\b\s*(?:=|:)?\s*({_DECIMAL})", re.IGNORECASE),
    ),
)

_LOA_PATTERN = re.compile(
    rf"\bLoA\b[^\d-]*({_DECIMAL})\s*(?:to|–|—|-)\s*({_DECIMAL})",
    re.IGNORECASE,
)
_RESPONSIVENESS_PATTERN = re.compile(
    rf"(?:effect\s*size|SRM|standardized\s*response\s*mean)\s*(?:=|:)?\s*({_DECIMAL})",
    re.IGNORECASE,
)
_DIF_NO_PATTERN = re.compile(r"\bno\s+dif\b[^.;]*", re.IGNORECASE)
_DIF_YES_PATTERN = re.compile(
    r"\b(?:significant|important)\s+dif\b[^.;]*|\bdif\s+was\s+found\b[^.;]*",
    re.IGNORECASE,
)
_SUBGROUP_TOKEN_PATTERN = re.compile(
    r"\b(men|women|male|female|adolescents|adults)\b",
    re.IGNORECASE,
)
_QTFA_ABBR_RE = re.compile(r"\bq\s*-?\s*tfa(?:\b|(?=[A-Za-z]))", re.IGNORECASE)
_QTFA_FULL_RE = re.compile(
    r"questionnaire\s+for\s+persons\s+with\s+a\s+transfemoral\s+amputation",
    re.IGNORECASE,
)
_PROMIS_ABBR_RE = re.compile(r"\bpromis(?:\b|(?=[A-Za-z]))", re.IGNORECASE)
_PROMIS_FULL_RE = re.compile(
    r"patient-?reported\s+outcomes\s+measurement\s+information\s+system",
    re.IGNORECASE,
)
_CITATION_RE = re.compile(r"\[[0-9,\s]+\]|\bet\s+al\.\b", re.IGNORECASE)
_SEM_TERM_RE = re.compile(r"\b(?:SEM|standard\s+error\s+of\s+measurement)\b", re.IGNORECASE)
_SDC_TERM_RE = re.compile(r"\bSDC\b", re.IGNORECASE)
_LOA_TERM_RE = re.compile(r"\b(?:LoA|limits?\s+of\s+agreement)\b", re.IGNORECASE)
_MCID_TERM_RE = re.compile(
    r"\b(?:MIC|MCID|MID|min(?:imum|imal)\s+clinically\s+important\s+difference)\b",
    re.IGNORECASE,
)
_MDC_TERM_RE = re.compile(r"\bmin(?:imum|imal)\s+detectable\s+change\b", re.IGNORECASE)
_INTERVAL_RE = re.compile(r"\b\d+\s*(?:month|months|year|years|week|weeks)\b", re.IGNORECASE)
_CHANGE_TERM_RE = re.compile(
    r"\b(change|changed|improv(?:e|ed|ement)|difference|mean\s+difference|increase|decrease)\b",
    re.IGNORECASE,
)


def extract_statistics_from_markdown_file(
    file_path: str | Path,
) -> ArticleStatisticsExtractionResult:
    """Extract statistic candidates from a markdown file."""

    parsed = parse_markdown_file(file_path)
    return extract_statistics_from_parsed_document(parsed)


def extract_statistics_from_parsed_document(
    parsed: ParsedMarkdownDocument,
) -> ArticleStatisticsExtractionResult:
    """Extract statistic candidates from parsed markdown spans."""

    candidates: list[StatisticCandidate] = []
    seen: set[tuple[object, ...]] = set()
    paragraph_method_labels = _build_paragraph_method_labels(parsed.sentences)

    for sentence in parsed.sentences:
        text = sentence.provenance.raw_text
        subgroup_label = _detect_subgroup_label(text)
        instrument_hints = _detect_instrument_hints(text)
        sentence_method_labels = _merge_method_labels(
            _detect_method_labels(text),
            paragraph_method_labels.get(sentence.parent_paragraph_id, ()),
        )

        _extract_single_value_stats(
            file_path=parsed.file_path,
            sentence=sentence,
            candidates=candidates,
            seen=seen,
            instrument_hints=instrument_hints,
            sentence_method_labels=sentence_method_labels,
        )
        _extract_loa(
            file_path=parsed.file_path,
            sentence=sentence,
            subgroup_label=subgroup_label,
            candidates=candidates,
            seen=seen,
            instrument_hints=instrument_hints,
            sentence_method_labels=sentence_method_labels,
        )
        _extract_dif_findings(
            file_path=parsed.file_path,
            sentence=sentence,
            subgroup_label=subgroup_label,
            candidates=candidates,
            seen=seen,
            instrument_hints=instrument_hints,
            sentence_method_labels=sentence_method_labels,
        )
        _extract_measurement_invariance(
            file_path=parsed.file_path,
            sentence=sentence,
            subgroup_label=subgroup_label,
            candidates=candidates,
            seen=seen,
            instrument_hints=instrument_hints,
            sentence_method_labels=sentence_method_labels,
        )
        _extract_known_groups_or_comparator(
            file_path=parsed.file_path,
            sentence=sentence,
            subgroup_label=subgroup_label,
            candidates=candidates,
            seen=seen,
            instrument_hints=instrument_hints,
            sentence_method_labels=sentence_method_labels,
        )
        _extract_responsiveness_related(
            file_path=parsed.file_path,
            sentence=sentence,
            subgroup_label=subgroup_label,
            candidates=candidates,
            seen=seen,
            instrument_hints=instrument_hints,
            sentence_method_labels=sentence_method_labels,
        )
        _extract_measurement_error_support_mentions(
            file_path=parsed.file_path,
            sentence=sentence,
            candidates=candidates,
            seen=seen,
            instrument_hints=instrument_hints,
            sentence_method_labels=sentence_method_labels,
        )
        _extract_longitudinal_responsiveness_candidate(
            file_path=parsed.file_path,
            sentence=sentence,
            candidates=candidates,
            seen=seen,
            instrument_hints=instrument_hints,
            sentence_method_labels=sentence_method_labels,
        )

    return ArticleStatisticsExtractionResult(
        id=_stable_id("stats", parsed.id, parsed.file_path),
        article_id=parsed.id,
        file_path=parsed.file_path,
        candidates=tuple(candidates),
    )


def _extract_single_value_stats(
    *,
    file_path: str,
    sentence: SentenceRecord,
    candidates: list[StatisticCandidate],
    seen: set[tuple[object, ...]],
    instrument_hints: tuple[str, ...],
    sentence_method_labels: tuple[EvidenceMethodLabel, ...],
) -> None:
    text = sentence.provenance.raw_text

    for statistic_type, pattern in _SINGLE_VALUE_PATTERNS:
        for match in pattern.finditer(text):
            raw_value = match.group(1)
            normalized = _to_float(raw_value)
            subgroup_label = _detect_subgroup_for_match(text, match.start(), match.end())
            _append_candidate(
                file_path=file_path,
                sentence=sentence,
                statistic_type=statistic_type,
                value_raw=raw_value,
                value_normalized=normalized,
                subgroup_label=subgroup_label,
                surrounding_text=text,
                instrument_hints=instrument_hints,
                method_labels=sentence_method_labels,
                candidates=candidates,
                seen=seen,
            )


def _extract_loa(
    *,
    file_path: str,
    sentence: SentenceRecord,
    subgroup_label: str | None,
    candidates: list[StatisticCandidate],
    seen: set[tuple[object, ...]],
    instrument_hints: tuple[str, ...],
    sentence_method_labels: tuple[EvidenceMethodLabel, ...],
) -> None:
    text = sentence.provenance.raw_text

    for match in _LOA_PATTERN.finditer(text):
        low_raw = match.group(1)
        high_raw = match.group(2)
        low = _to_float(low_raw)
        high = _to_float(high_raw)
        _append_candidate(
            file_path=file_path,
            sentence=sentence,
            statistic_type=StatisticType.LOA,
            value_raw=f"{low_raw} to {high_raw}",
            value_normalized=(low, high),
            subgroup_label=subgroup_label,
            surrounding_text=text,
            instrument_hints=instrument_hints,
            method_labels=sentence_method_labels,
            candidates=candidates,
            seen=seen,
        )


def _extract_dif_findings(
    *,
    file_path: str,
    sentence: SentenceRecord,
    subgroup_label: str | None,
    candidates: list[StatisticCandidate],
    seen: set[tuple[object, ...]],
    instrument_hints: tuple[str, ...],
    sentence_method_labels: tuple[EvidenceMethodLabel, ...],
) -> None:
    text = sentence.provenance.raw_text
    text_lower = text.lower()
    if "dif" not in text_lower:
        return

    for match in _DIF_NO_PATTERN.finditer(text):
        _append_candidate(
            file_path=file_path,
            sentence=sentence,
            statistic_type=StatisticType.DIF_FINDING,
            value_raw=match.group(0),
            value_normalized="no_dif",
            subgroup_label=subgroup_label,
            surrounding_text=text,
            instrument_hints=instrument_hints,
            method_labels=sentence_method_labels,
            candidates=candidates,
            seen=seen,
        )

    for match in _DIF_YES_PATTERN.finditer(text):
        _append_candidate(
            file_path=file_path,
            sentence=sentence,
            statistic_type=StatisticType.DIF_FINDING,
            value_raw=match.group(0),
            value_normalized="dif_present",
            subgroup_label=subgroup_label,
            surrounding_text=text,
            instrument_hints=instrument_hints,
            method_labels=sentence_method_labels,
            candidates=candidates,
            seen=seen,
        )


def _extract_measurement_invariance(
    *,
    file_path: str,
    sentence: SentenceRecord,
    subgroup_label: str | None,
    candidates: list[StatisticCandidate],
    seen: set[tuple[object, ...]],
    instrument_hints: tuple[str, ...],
    sentence_method_labels: tuple[EvidenceMethodLabel, ...],
) -> None:
    text = sentence.provenance.raw_text
    text_lower = text.lower()
    if "invariance" not in text_lower:
        return

    normalized = "mentioned"
    if "not supported" in text_lower or "violated" in text_lower:
        normalized = "not_supported"
    elif "supported" in text_lower or "holds" in text_lower:
        normalized = "supported"

    _append_candidate(
        file_path=file_path,
        sentence=sentence,
        statistic_type=StatisticType.MEASUREMENT_INVARIANCE_FINDING,
        value_raw=text,
        value_normalized=normalized,
        subgroup_label=subgroup_label,
        surrounding_text=text,
        instrument_hints=instrument_hints,
        method_labels=sentence_method_labels,
        candidates=candidates,
        seen=seen,
    )


def _extract_known_groups_or_comparator(
    *,
    file_path: str,
    sentence: SentenceRecord,
    subgroup_label: str | None,
    candidates: list[StatisticCandidate],
    seen: set[tuple[object, ...]],
    instrument_hints: tuple[str, ...],
    sentence_method_labels: tuple[EvidenceMethodLabel, ...],
) -> None:
    text = sentence.provenance.raw_text
    text_lower = text.lower()

    if (
        "known-groups" not in text_lower
        and "known groups" not in text_lower
        and "comparator" not in text_lower
    ):
        return

    normalized = "reported"
    if any(token in text_lower for token in ("significant", "higher", "lower", "different")):
        normalized = "difference_reported"

    _append_candidate(
        file_path=file_path,
        sentence=sentence,
        statistic_type=StatisticType.KNOWN_GROUPS_OR_COMPARATOR_RESULT,
        value_raw=text,
        value_normalized=normalized,
        subgroup_label=subgroup_label,
        surrounding_text=text,
        instrument_hints=instrument_hints,
        method_labels=sentence_method_labels,
        candidates=candidates,
        seen=seen,
    )


def _extract_responsiveness_related(
    *,
    file_path: str,
    sentence: SentenceRecord,
    subgroup_label: str | None,
    candidates: list[StatisticCandidate],
    seen: set[tuple[object, ...]],
    instrument_hints: tuple[str, ...],
    sentence_method_labels: tuple[EvidenceMethodLabel, ...],
) -> None:
    text = sentence.provenance.raw_text
    text_lower = text.lower()

    if "responsiveness" not in text_lower:
        return

    hypothesis_status = _detect_responsiveness_hypothesis_status(text_lower)

    found_numeric = False
    for match in _RESPONSIVENESS_PATTERN.finditer(text):
        found_numeric = True
        raw_value = match.group(1)
        normalized = _to_float(raw_value)
        _append_candidate(
            file_path=file_path,
            sentence=sentence,
            statistic_type=StatisticType.RESPONSIVENESS_RELATED_STATISTIC,
            value_raw=raw_value,
            value_normalized=normalized,
            subgroup_label=subgroup_label,
            surrounding_text=text,
            instrument_hints=instrument_hints,
            method_labels=sentence_method_labels,
            responsiveness_hypothesis_status=hypothesis_status,
            candidates=candidates,
            seen=seen,
        )

    if not found_numeric:
        _append_candidate(
            file_path=file_path,
            sentence=sentence,
            statistic_type=StatisticType.RESPONSIVENESS_RELATED_STATISTIC,
            value_raw=text,
            value_normalized="mentioned",
            subgroup_label=subgroup_label,
            surrounding_text=text,
            instrument_hints=instrument_hints,
            method_labels=sentence_method_labels,
            responsiveness_hypothesis_status=hypothesis_status,
            candidates=candidates,
            seen=seen,
        )


def _extract_measurement_error_support_mentions(
    *,
    file_path: str,
    sentence: SentenceRecord,
    candidates: list[StatisticCandidate],
    seen: set[tuple[object, ...]],
    instrument_hints: tuple[str, ...],
    sentence_method_labels: tuple[EvidenceMethodLabel, ...],
) -> None:
    text = sentence.provenance.raw_text

    mention_rules: tuple[tuple[StatisticType, re.Pattern[str], str], ...] = (
        (StatisticType.MIC, _MCID_TERM_RE, "mcid_term"),
        (StatisticType.SEM, _SEM_TERM_RE, "sem_term"),
        (StatisticType.SDC, _SDC_TERM_RE, "sdc_term"),
        (StatisticType.LOA, _LOA_TERM_RE, "loa_term"),
        (StatisticType.SDC, _MDC_TERM_RE, "minimal_detectable_change"),
    )

    for statistic_type, pattern, label in mention_rules:
        match = pattern.search(text)
        if not match:
            continue

        if _has_sentence_candidate(candidates, sentence.id, statistic_type):
            continue

        _append_candidate(
            file_path=file_path,
            sentence=sentence,
            statistic_type=statistic_type,
            value_raw=label,
            value_normalized="mentioned",
            subgroup_label=None,
            surrounding_text=text,
            instrument_hints=instrument_hints,
            method_labels=sentence_method_labels,
            candidates=candidates,
            seen=seen,
        )


def _extract_longitudinal_responsiveness_candidate(
    *,
    file_path: str,
    sentence: SentenceRecord,
    candidates: list[StatisticCandidate],
    seen: set[tuple[object, ...]],
    instrument_hints: tuple[str, ...],
    sentence_method_labels: tuple[EvidenceMethodLabel, ...],
) -> None:
    text = sentence.provenance.raw_text
    text_lower = text.lower()

    if not instrument_hints:
        return
    if "baseline" not in text_lower:
        return
    if "follow-up" not in text_lower and not _INTERVAL_RE.search(text_lower):
        return
    if not _CHANGE_TERM_RE.search(text_lower):
        return

    hypothesis_status = _detect_responsiveness_hypothesis_status(text_lower)

    _append_candidate(
        file_path=file_path,
        sentence=sentence,
        statistic_type=StatisticType.RESPONSIVENESS_RELATED_STATISTIC,
        value_raw="longitudinal_change_reported",
        value_normalized="longitudinal_change_reported",
        subgroup_label=None,
        surrounding_text=text,
        instrument_hints=instrument_hints,
        method_labels=sentence_method_labels,
        responsiveness_hypothesis_status=hypothesis_status,
        candidates=candidates,
        seen=seen,
    )


def _append_candidate(
    *,
    file_path: str,
    sentence: SentenceRecord,
    statistic_type: StatisticType,
    value_raw: str,
    value_normalized: float | tuple[float, float] | str | None,
    subgroup_label: str | None,
    surrounding_text: str,
    instrument_hints: tuple[str, ...],
    method_labels: tuple[EvidenceMethodLabel, ...],
    candidates: list[StatisticCandidate],
    seen: set[tuple[object, ...]],
    evidence_source: EvidenceSourceType | None = None,
    measurement_routes: tuple[MeasurementPropertyRoute, ...] | None = None,
    responsiveness_hypothesis_status: ResponsivenessHypothesisStatus | None = None,
) -> None:
    normalized_raw = value_raw.strip()
    if not normalized_raw:
        return

    source = evidence_source or _classify_evidence_source(
        sentence=sentence,
        statistic_type=statistic_type,
        text=surrounding_text,
        method_labels=method_labels,
    )
    routes = measurement_routes or _default_routes(
        statistic_type=statistic_type,
        evidence_source=source,
        method_labels=method_labels,
    )
    hypothesis_status = responsiveness_hypothesis_status
    if (
        statistic_type is StatisticType.RESPONSIVENESS_RELATED_STATISTIC
        and hypothesis_status is None
    ):
        hypothesis_status = _detect_responsiveness_hypothesis_status(surrounding_text.lower())

    key = (
        statistic_type.value,
        normalized_raw,
        value_normalized,
        subgroup_label,
        sentence.id,
        source.value,
        tuple(route.value for route in routes),
        tuple(label.value for label in method_labels),
        tuple(instrument_hints),
        hypothesis_status.value if hypothesis_status else "",
    )
    if key in seen:
        return
    seen.add(key)

    candidates.append(
        StatisticCandidate(
            id=_stable_id(
                "stat",
                file_path,
                statistic_type.value,
                sentence.id,
                normalized_raw,
                str(value_normalized),
                subgroup_label or "",
                source.value,
                ",".join(route.value for route in routes),
                ",".join(label.value for label in method_labels),
                ",".join(instrument_hints),
                hypothesis_status.value if hypothesis_status else "",
            ),
            statistic_type=statistic_type,
            value_raw=normalized_raw,
            value_normalized=value_normalized,
            subgroup_label=subgroup_label,
            evidence_span_ids=(sentence.id,),
            surrounding_text=surrounding_text,
            instrument_name_hints=instrument_hints,
            evidence_source=source,
            measurement_property_routes=routes,
            method_labels=method_labels,
            responsiveness_hypothesis_status=hypothesis_status,
        )
    )


def _classify_evidence_source(
    *,
    sentence: SentenceRecord,
    statistic_type: StatisticType,
    text: str,
    method_labels: tuple[EvidenceMethodLabel, ...],
) -> EvidenceSourceType:
    text_lower = text.lower()
    heading_tokens = " ".join(sentence.heading_path).lower()

    if "references" in heading_tokens:
        return EvidenceSourceType.BACKGROUND_CITATION

    if _CITATION_RE.search(text) and any(
        token in text_lower
        for token in (
            "validity",
            "reliability",
            "validated",
            "demonstrated",
            "previous",
            "prior",
            "described by",
        )
    ):
        return EvidenceSourceType.BACKGROUND_CITATION

    if "introduction" in heading_tokens and _CITATION_RE.search(text):
        return EvidenceSourceType.BACKGROUND_CITATION

    if _is_interpretability_context(
        statistic_type=statistic_type,
        text_lower=text_lower,
        method_labels=method_labels,
    ):
        return EvidenceSourceType.INTERPRETABILITY_ONLY

    return EvidenceSourceType.CURRENT_STUDY


def _is_interpretability_context(
    *,
    statistic_type: StatisticType,
    text_lower: str,
    method_labels: tuple[EvidenceMethodLabel, ...],
) -> bool:
    interpretability_tokens = (
        "mcid",
        "mic",
        "mid",
        "minimum clinically important difference",
        "minimal clinically important difference",
        "minimal detectable change",
        "distribution method",
        "anchor-based",
        "anchor based",
        "sanity check",
    )

    if any(token in text_lower for token in interpretability_tokens):
        return True

    return statistic_type in (
        StatisticType.MIC,
        StatisticType.SEM,
        StatisticType.SDC,
        StatisticType.LOA,
    ) and bool(method_labels)


def _default_routes(
    *,
    statistic_type: StatisticType,
    evidence_source: EvidenceSourceType,
    method_labels: tuple[EvidenceMethodLabel, ...],
) -> tuple[MeasurementPropertyRoute, ...]:
    routes: list[MeasurementPropertyRoute] = []

    if statistic_type in (
        StatisticType.CFI,
        StatisticType.TLI,
        StatisticType.RMSEA,
        StatisticType.SRMR,
    ):
        routes.append(MeasurementPropertyRoute.STRUCTURAL_VALIDITY)
    elif statistic_type is StatisticType.CRONBACH_ALPHA:
        routes.append(MeasurementPropertyRoute.INTERNAL_CONSISTENCY)
    elif statistic_type in (StatisticType.ICC, StatisticType.WEIGHTED_KAPPA):
        routes.append(MeasurementPropertyRoute.RELIABILITY)
    elif statistic_type in (StatisticType.SEM, StatisticType.SDC, StatisticType.LOA):
        routes.append(MeasurementPropertyRoute.MEASUREMENT_ERROR_SUPPORT)
    elif statistic_type is StatisticType.MIC:
        routes.extend(
            (
                MeasurementPropertyRoute.INTERPRETABILITY,
                MeasurementPropertyRoute.MEASUREMENT_ERROR_SUPPORT,
            )
        )
    elif statistic_type is StatisticType.RESPONSIVENESS_RELATED_STATISTIC:
        routes.append(MeasurementPropertyRoute.RESPONSIVENESS)
    elif statistic_type in (
        StatisticType.AUC,
        StatisticType.CORRELATION,
        StatisticType.KNOWN_GROUPS_OR_COMPARATOR_RESULT,
        StatisticType.DIF_FINDING,
        StatisticType.MEASUREMENT_INVARIANCE_FINDING,
    ):
        routes.append(MeasurementPropertyRoute.HYPOTHESES_TESTING_FOR_CONSTRUCT_VALIDITY)

    if (
        evidence_source is EvidenceSourceType.INTERPRETABILITY_ONLY
        and MeasurementPropertyRoute.INTERPRETABILITY not in routes
    ):
        routes.append(MeasurementPropertyRoute.INTERPRETABILITY)

    if (
        any(
            label
            in (
                EvidenceMethodLabel.ANCHOR_BASED,
                EvidenceMethodLabel.DISTRIBUTION_BASED,
                EvidenceMethodLabel.MINIMAL_DETECTABLE_CHANGE,
            )
            for label in method_labels
        )
        and MeasurementPropertyRoute.INTERPRETABILITY not in routes
    ):
        routes.append(MeasurementPropertyRoute.INTERPRETABILITY)

    deduplicated = tuple(dict.fromkeys(routes))
    return deduplicated


def _detect_subgroup_label(text: str) -> str | None:
    text_lower = text.lower()
    mentions = {m.group(1).lower() for m in _SUBGROUP_TOKEN_PATTERN.finditer(text_lower)}
    if len(mentions) > 1:
        return None

    explicit = re.search(r"\b(?:for|in)\s+(men|women|male|female|adolescents|adults)\b", text_lower)
    if explicit:
        return explicit.group(1)

    parenthetical = re.search(r"\((men|women|male|female)\)", text_lower)
    if parenthetical:
        return parenthetical.group(1)

    group_named = re.search(r"\b(?:subgroup|group)\s+([a-z0-9_-]+)\b", text_lower)
    if group_named:
        return group_named.group(1)

    if len(mentions) == 1:
        return next(iter(mentions))

    return None


def _detect_instrument_hints(text: str) -> tuple[str, ...]:
    hints: list[str] = []

    if _QTFA_FULL_RE.search(text) or _QTFA_ABBR_RE.search(text):
        hints.append("Q-TFA")
    if _PROMIS_FULL_RE.search(text) or _PROMIS_ABBR_RE.search(text):
        hints.append("PROMIS")

    return tuple(dict.fromkeys(hints))


def _detect_method_labels(text: str) -> tuple[EvidenceMethodLabel, ...]:
    text_lower = text.lower()
    labels: list[EvidenceMethodLabel] = []

    if "anchor-based" in text_lower or "anchor based" in text_lower:
        labels.append(EvidenceMethodLabel.ANCHOR_BASED)
    if "distribution-based" in text_lower or "distribution method" in text_lower:
        labels.append(EvidenceMethodLabel.DISTRIBUTION_BASED)
    if _SEM_TERM_RE.search(text):
        labels.append(EvidenceMethodLabel.SEM_BASED)
    if _SDC_TERM_RE.search(text):
        labels.append(EvidenceMethodLabel.SDC_BASED)
    if _LOA_TERM_RE.search(text):
        labels.append(EvidenceMethodLabel.LOA_BASED)
    if _MDC_TERM_RE.search(text):
        labels.append(EvidenceMethodLabel.MINIMAL_DETECTABLE_CHANGE)
    if "test-retest reliability" in text_lower or "reliability coefficient" in text_lower:
        labels.append(EvidenceMethodLabel.TEST_RETEST_RELIABILITY)
        if _SEM_TERM_RE.search(text) or _MDC_TERM_RE.search(text):
            labels.append(EvidenceMethodLabel.DISTRIBUTION_BASED)

    return tuple(dict.fromkeys(labels))


def _build_paragraph_method_labels(
    sentences: tuple[SentenceRecord, ...],
) -> dict[StableId, tuple[EvidenceMethodLabel, ...]]:
    by_paragraph: dict[StableId, list[EvidenceMethodLabel]] = {}
    for sentence in sentences:
        labels = _detect_method_labels(sentence.provenance.raw_text)
        if not labels:
            continue
        bucket = by_paragraph.setdefault(sentence.parent_paragraph_id, [])
        bucket.extend(labels)

    return {
        paragraph_id: tuple(dict.fromkeys(labels)) for paragraph_id, labels in by_paragraph.items()
    }


def _merge_method_labels(
    sentence_labels: tuple[EvidenceMethodLabel, ...],
    paragraph_labels: tuple[EvidenceMethodLabel, ...],
) -> tuple[EvidenceMethodLabel, ...]:
    merged = list(sentence_labels)
    merged.extend(paragraph_labels)
    return tuple(dict.fromkeys(merged))


def _detect_responsiveness_hypothesis_status(text_lower: str) -> ResponsivenessHypothesisStatus:
    if any(
        token in text_lower
        for token in (
            "a priori hypothesis",
            "a-priori hypothesis",
            "predefined hypothesis",
            "pre-specified hypothesis",
        )
    ):
        return ResponsivenessHypothesisStatus.PREDEFINED

    if any(
        token in text_lower
        for token in (
            "no predefined hypothesis",
            "without predefined hypothesis",
            "hypotheses were not predefined",
        )
    ):
        return ResponsivenessHypothesisStatus.NOT_PREDEFINED

    return ResponsivenessHypothesisStatus.NOT_REPORTED


def _detect_subgroup_for_match(
    text: str,
    match_start: int,
    match_end: int,
) -> str | None:
    clause = _extract_clause_for_match(text, match_start, match_end)
    return _detect_subgroup_label(clause)


def _extract_clause_for_match(text: str, match_start: int, match_end: int) -> str:
    left_boundary = max(text.rfind(";", 0, match_start), text.rfind(".", 0, match_start))

    right_candidates = [
        idx for idx in (text.find(";", match_end), text.find(".", match_end)) if idx != -1
    ]
    right_boundary = min(right_candidates) if right_candidates else len(text)

    clause_start = left_boundary + 1 if left_boundary >= 0 else 0
    return text[clause_start:right_boundary].strip()


def _has_sentence_candidate(
    candidates: list[StatisticCandidate],
    sentence_id: StableId,
    statistic_type: StatisticType,
) -> bool:
    return any(
        candidate.statistic_type is statistic_type and sentence_id in candidate.evidence_span_ids
        for candidate in candidates
    )


def _to_float(raw_value: str) -> float:
    normalized = raw_value.strip().replace(",", ".")
    return float(normalized)


def _stable_id(prefix: str, *parts: object) -> StableId:
    serialized = "|".join(str(part) for part in parts)
    digest = hashlib.sha1(f"{prefix}|{serialized}".encode()).hexdigest()[:16]
    return f"{prefix}.{digest}"
