"""Deterministic candidate statistic extraction without threshold interpretation."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from cosmin_assistant.extract.markdown_parser import parse_markdown_file
from cosmin_assistant.extract.spans import ParsedMarkdownDocument, SentenceRecord
from cosmin_assistant.extract.statistics_models import (
    ArticleStatisticsExtractionResult,
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
        re.compile(rf"\bMIC\b\s*(?:=|:)?\s*({_DECIMAL})", re.IGNORECASE),
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

    for sentence in parsed.sentences:
        subgroup_label = _detect_subgroup_label(sentence.provenance.raw_text)
        _extract_single_value_stats(parsed.file_path, sentence, candidates, seen)
        _extract_loa(parsed.file_path, sentence, subgroup_label, candidates, seen)
        _extract_dif_findings(parsed.file_path, sentence, subgroup_label, candidates, seen)
        _extract_measurement_invariance(
            parsed.file_path, sentence, subgroup_label, candidates, seen
        )
        _extract_known_groups_or_comparator(
            parsed.file_path, sentence, subgroup_label, candidates, seen
        )
        _extract_responsiveness_related(
            parsed.file_path, sentence, subgroup_label, candidates, seen
        )

    return ArticleStatisticsExtractionResult(
        id=_stable_id("stats", parsed.id, parsed.file_path),
        article_id=parsed.id,
        file_path=parsed.file_path,
        candidates=tuple(candidates),
    )


def _extract_single_value_stats(
    file_path: str,
    sentence: SentenceRecord,
    candidates: list[StatisticCandidate],
    seen: set[tuple[object, ...]],
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
                candidates=candidates,
                seen=seen,
            )


def _extract_loa(
    file_path: str,
    sentence: SentenceRecord,
    subgroup_label: str | None,
    candidates: list[StatisticCandidate],
    seen: set[tuple[object, ...]],
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
            candidates=candidates,
            seen=seen,
        )


def _extract_dif_findings(
    file_path: str,
    sentence: SentenceRecord,
    subgroup_label: str | None,
    candidates: list[StatisticCandidate],
    seen: set[tuple[object, ...]],
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
            candidates=candidates,
            seen=seen,
        )


def _extract_measurement_invariance(
    file_path: str,
    sentence: SentenceRecord,
    subgroup_label: str | None,
    candidates: list[StatisticCandidate],
    seen: set[tuple[object, ...]],
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
        candidates=candidates,
        seen=seen,
    )


def _extract_known_groups_or_comparator(
    file_path: str,
    sentence: SentenceRecord,
    subgroup_label: str | None,
    candidates: list[StatisticCandidate],
    seen: set[tuple[object, ...]],
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
        candidates=candidates,
        seen=seen,
    )


def _extract_responsiveness_related(
    file_path: str,
    sentence: SentenceRecord,
    subgroup_label: str | None,
    candidates: list[StatisticCandidate],
    seen: set[tuple[object, ...]],
) -> None:
    text = sentence.provenance.raw_text
    text_lower = text.lower()

    if "responsiveness" not in text_lower:
        return

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
    candidates: list[StatisticCandidate],
    seen: set[tuple[object, ...]],
) -> None:
    normalized_raw = value_raw.strip()
    if not normalized_raw:
        return

    key = (
        statistic_type.value,
        normalized_raw,
        value_normalized,
        subgroup_label,
        sentence.id,
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
            ),
            statistic_type=statistic_type,
            value_raw=normalized_raw,
            value_normalized=value_normalized,
            subgroup_label=subgroup_label,
            evidence_span_ids=(sentence.id,),
            surrounding_text=surrounding_text,
        )
    )


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


def _to_float(raw_value: str) -> float:
    normalized = raw_value.strip().replace(",", ".")
    return float(normalized)


def _stable_id(prefix: str, *parts: object) -> StableId:
    serialized = "|".join(str(part) for part in parts)
    digest = hashlib.sha1(f"{prefix}|{serialized}".encode()).hexdigest()[:16]
    return f"{prefix}.{digest}"
