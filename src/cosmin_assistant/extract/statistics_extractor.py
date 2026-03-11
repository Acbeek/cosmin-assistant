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
        re.compile(
            rf"(?:cronbach(?:'s)?\s*alpha|α)\s*(?:=|:|was|of)?\s*({_DECIMAL})",
            re.IGNORECASE,
        ),
    ),
    (
        StatisticType.KR20,
        re.compile(
            rf"(?:kuder-?richardson(?:\s*formula)?\s*20|kr-?20(?:\s*coefficient)?)"
            rf"\s*(?:=|:|was|of)?\s*({_DECIMAL})",
            re.IGNORECASE,
        ),
    ),
    (
        StatisticType.ICC,
        re.compile(
            rf"\bICC(?:\s*[\]\)\}}])?(?:\s*\([^)]+\))?\s*(?:=|:|was|of)?\s*({_DECIMAL})",
            re.IGNORECASE,
        ),
    ),
    (
        StatisticType.ICC,
        re.compile(
            rf"\b(?:intra|inter)class\s+correlation\s+coefficient(?:s)?"
            rf"(?:\s*\[[^\]]+\])?\s*(?:=|:|was|of)?\s*({_DECIMAL})",
            re.IGNORECASE,
        ),
    ),
    (
        StatisticType.WEIGHTED_KAPPA,
        re.compile(
            rf"(?:weighted\s*kappa|weighted\s+cohen(?:'s)?\s*kappa|κw)"
            rf"\s*(?:=|:|was|of)?\s*({_DECIMAL})",
            re.IGNORECASE,
        ),
    ),
    (
        StatisticType.KAPPA,
        re.compile(
            rf"(?:cohen(?:'s)?\s+kappa(?:\s+coefficient)?|kappa\s+coefficient|κ)"
            rf"\s*(?:=|:|was|of)?\s*({_DECIMAL})",
            re.IGNORECASE,
        ),
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
            rf"\b(?:MIC|MCID|MID)\b(?!\s*\(\s*n\s*=)[^=:\n]{{0,60}}"
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
_CITATION_RE = re.compile(
    r"\[[0-9,\s]+\]|<sup>\s*\d+(?:\s*[-,]\s*\d+)*\s*</sup>|\bet\s+al\.\b",
    re.IGNORECASE,
)
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
_NOT_ASSESSED_RE = re.compile(
    r"\b(not assessed|were not assessed|not evaluated|"
    r"impossible to verify|lack of a gold standard)\b",
    re.IGNORECASE,
)
_COMPARATOR_CONTEXT_RE = re.compile(
    r"\b(by comparing|compared with|comparison(?:s)? with|correlat(?:ed|ion(?:s)?) "
    r"(?:between|with)|association (?:between|with)|with the)\b",
    re.IGNORECASE,
)
_INTERNAL_STRUCTURE_SIGNAL_RE = re.compile(
    r"\b(?:rasch|irt|item\s+fit|infit|outfit|local\s+dependence|"
    r"local\s+independence|unidimensional(?:ity)?|dimensionality|"
    r"residual\s+pca|threshold\s+ordering)\b",
    re.IGNORECASE,
)
_OUTCOME_LIST_RE = re.compile(
    r"\b(?:outcome\s+measures?|outcomes?)\s*(?:include(?:d)?|consisted\s+of|"
    r"were\s+assessed\s+with|were\s+measured\s+with|were\s+the)\s*[:=-]?\s*([^.]+)",
    re.IGNORECASE,
)
_GENERIC_INSTRUMENT_TOKEN_RE = re.compile(
    r"\b([A-Z][A-Z0-9]+(?:-[A-Z0-9]+)+|[A-Z]{3,12}(?:\s*\d+(?:\.\d+)*)?)\b"
)
_GENERIC_INSTRUMENT_CONTEXT_RE = re.compile(
    r"\b(?:instrument|questionnaire|scale|survey|measure|tool|test|score|scores|"
    r"outcome|comparing|correlation|validity|reliability)\b",
    re.IGNORECASE,
)
_RATER_RELIABILITY_SPAN_RE = re.compile(
    r"\b(?:inter-?rater|intra-?rater|test-?retest(?:/intra-?rater)?)\s+reliability\b[^;\n]{0,160}",
    re.IGNORECASE,
)
_GENERIC_INSTRUMENT_STOPWORDS = {
    "ICC",
    "SEM",
    "SDC",
    "LOA",
    "MIC",
    "MCID",
    "MID",
    "CFI",
    "TLI",
    "RMSEA",
    "SRMR",
    "AUC",
    "CI",
    "SD",
    "SE",
    "SPSS",
    "KR-20",
    "KR20",
    "MWT",
    "R",
}
_LOCAL_TARGET_VALUE_RE = re.compile(
    r"(?:for|of)\s+([A-Za-z][A-Za-z0-9\- ]{1,60})\s*(?:=|:)\s*$",
    re.IGNORECASE,
)
_ADDITIONAL_VALUE_PAIR_RE = re.compile(
    rf"(?:,|and)\s*([A-Za-z][A-Za-z0-9\- ]{{1,60}}?)\s*(?:=|:)\s*({_DECIMAL})",
    re.IGNORECASE,
)
_MIC_VALUE_PAIR_RE = re.compile(
    rf"([A-Za-z][A-Za-z0-9\- ]{{1,60}}?)\s*(?:=|:)\s*({_DECIMAL})",
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
    paragraph_instrument_hints = _build_paragraph_instrument_hints(parsed.sentences)

    for sentence in parsed.sentences:
        text = sentence.provenance.raw_text
        subgroup_label = _detect_subgroup_label(text)
        instrument_hints = _merge_instrument_hints(
            _detect_instrument_hints(text),
            paragraph_instrument_hints.get(sentence.parent_paragraph_id, ()),
        )
        comparator_hints = _detect_comparator_instrument_hints(text)
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
            comparator_hints=comparator_hints,
            sentence_method_labels=sentence_method_labels,
        )
        _extract_rater_reliability_coefficients(
            file_path=parsed.file_path,
            sentence=sentence,
            subgroup_label=subgroup_label,
            candidates=candidates,
            seen=seen,
            instrument_hints=instrument_hints,
            comparator_hints=comparator_hints,
            sentence_method_labels=sentence_method_labels,
        )
        _extract_table_internal_consistency_rows(
            file_path=parsed.file_path,
            sentence=sentence,
            candidates=candidates,
            seen=seen,
            comparator_hints=comparator_hints,
            sentence_method_labels=sentence_method_labels,
        )
        _extract_loa(
            file_path=parsed.file_path,
            sentence=sentence,
            subgroup_label=subgroup_label,
            candidates=candidates,
            seen=seen,
            instrument_hints=instrument_hints,
            comparator_hints=comparator_hints,
            sentence_method_labels=sentence_method_labels,
        )
        _extract_dif_findings(
            file_path=parsed.file_path,
            sentence=sentence,
            subgroup_label=subgroup_label,
            candidates=candidates,
            seen=seen,
            instrument_hints=instrument_hints,
            comparator_hints=comparator_hints,
            sentence_method_labels=sentence_method_labels,
        )
        _extract_measurement_invariance(
            file_path=parsed.file_path,
            sentence=sentence,
            subgroup_label=subgroup_label,
            candidates=candidates,
            seen=seen,
            instrument_hints=instrument_hints,
            comparator_hints=comparator_hints,
            sentence_method_labels=sentence_method_labels,
        )
        _extract_known_groups_or_comparator(
            file_path=parsed.file_path,
            sentence=sentence,
            subgroup_label=subgroup_label,
            candidates=candidates,
            seen=seen,
            instrument_hints=instrument_hints,
            comparator_hints=comparator_hints,
            sentence_method_labels=sentence_method_labels,
        )
        _extract_internal_structure_signals(
            file_path=parsed.file_path,
            sentence=sentence,
            subgroup_label=subgroup_label,
            candidates=candidates,
            seen=seen,
            instrument_hints=instrument_hints,
            comparator_hints=comparator_hints,
            sentence_method_labels=sentence_method_labels,
        )
        _extract_responsiveness_related(
            file_path=parsed.file_path,
            sentence=sentence,
            subgroup_label=subgroup_label,
            candidates=candidates,
            seen=seen,
            instrument_hints=instrument_hints,
            comparator_hints=comparator_hints,
            sentence_method_labels=sentence_method_labels,
        )
        _extract_measurement_error_support_mentions(
            file_path=parsed.file_path,
            sentence=sentence,
            candidates=candidates,
            seen=seen,
            instrument_hints=instrument_hints,
            comparator_hints=comparator_hints,
            sentence_method_labels=sentence_method_labels,
        )
        _extract_longitudinal_responsiveness_candidate(
            file_path=parsed.file_path,
            sentence=sentence,
            candidates=candidates,
            seen=seen,
            instrument_hints=instrument_hints,
            comparator_hints=comparator_hints,
            sentence_method_labels=sentence_method_labels,
        )

    direct_ids, background_ids, interpretability_ids, comparator_ids = _partition_candidate_ids(
        candidates
    )

    return ArticleStatisticsExtractionResult(
        id=_stable_id("stats", parsed.id, parsed.file_path),
        article_id=parsed.id,
        file_path=parsed.file_path,
        candidates=tuple(candidates),
        direct_current_study_ids=direct_ids,
        background_citation_ids=background_ids,
        interpretability_support_ids=interpretability_ids,
        comparator_instrument_context_ids=comparator_ids,
    )


def _extract_single_value_stats(
    *,
    file_path: str,
    sentence: SentenceRecord,
    candidates: list[StatisticCandidate],
    seen: set[tuple[object, ...]],
    instrument_hints: tuple[str, ...],
    comparator_hints: tuple[str, ...],
    sentence_method_labels: tuple[EvidenceMethodLabel, ...],
) -> None:
    text = sentence.provenance.raw_text
    sentence_subgroup_label = _detect_subgroup_label(text)

    for statistic_type, pattern in _SINGLE_VALUE_PATTERNS:
        matches = list(pattern.finditer(text))
        if statistic_type is StatisticType.MIC and not matches:
            _extract_mic_value_pairs_without_inline_numeric(
                file_path=file_path,
                sentence=sentence,
                sentence_text=text,
                subgroup_label=sentence_subgroup_label,
                candidates=candidates,
                seen=seen,
                comparator_hints=comparator_hints,
                method_labels=sentence_method_labels,
            )
            continue

        for match in matches:
            raw_value = match.group(1)
            normalized = _to_float(raw_value)
            subgroup_label = _detect_subgroup_for_match(text, match.start(), match.end())
            clause_text = _extract_clause_for_match(text, match.start(), match.end())
            clause_hints = _detect_instrument_hints(clause_text)
            clause_comparator_hints = _detect_comparator_instrument_hints(clause_text)
            clause_method_labels = _detect_method_labels(clause_text)
            resolved_hints = clause_hints or instrument_hints
            resolved_comparator_hints = clause_comparator_hints or comparator_hints
            if statistic_type is StatisticType.MIC:
                local_target_hints = _detect_local_target_hints_for_value(
                    text=text,
                    value_start=match.start(1),
                )
                if local_target_hints:
                    resolved_hints = local_target_hints
            if (
                statistic_type in (StatisticType.CORRELATION, StatisticType.AUC)
                and len(resolved_hints) < 2
                and instrument_hints
            ):
                resolved_hints = tuple(dict.fromkeys((*resolved_hints, *instrument_hints)))
            if (
                statistic_type in (StatisticType.CORRELATION, StatisticType.AUC)
                and len(resolved_comparator_hints) < 2
                and comparator_hints
            ):
                resolved_comparator_hints = tuple(
                    dict.fromkeys((*resolved_comparator_hints, *comparator_hints))
                )
            _append_candidate(
                file_path=file_path,
                sentence=sentence,
                statistic_type=statistic_type,
                value_raw=raw_value,
                value_normalized=normalized,
                subgroup_label=subgroup_label,
                surrounding_text=clause_text or text,
                instrument_hints=resolved_hints,
                comparator_hints=resolved_comparator_hints,
                method_labels=clause_method_labels or sentence_method_labels,
                candidates=candidates,
                seen=seen,
            )
            if statistic_type is StatisticType.MIC:
                _extract_additional_mic_values(
                    file_path=file_path,
                    sentence=sentence,
                    sentence_text=text,
                    tail_start=match.end(1),
                    subgroup_label=subgroup_label,
                    candidates=candidates,
                    seen=seen,
                    comparator_hints=resolved_comparator_hints,
                    method_labels=clause_method_labels or sentence_method_labels,
                )


def _extract_table_internal_consistency_rows(
    *,
    file_path: str,
    sentence: SentenceRecord,
    candidates: list[StatisticCandidate],
    seen: set[tuple[object, ...]],
    comparator_hints: tuple[str, ...],
    sentence_method_labels: tuple[EvidenceMethodLabel, ...],
) -> None:
    text = sentence.provenance.raw_text
    text_lower = text.lower()
    if "<table" not in text_lower:
        return
    if "cronbach" not in text_lower and "kr-20" not in text_lower and "kr20" not in text_lower:
        return

    rows = _extract_table_rows(text)
    if not rows:
        return

    header_hints = _table_column_instrument_hints(rows)
    if not header_hints:
        return

    for row in rows:
        if not row:
            continue
        label = _clean_table_cell_text(row[0]).lower()
        statistic_type: StatisticType | None = None
        if "cronbach" in label or "alpha" in label:
            statistic_type = StatisticType.CRONBACH_ALPHA
        elif "kr-20" in label or "kr20" in label or "kuder" in label:
            statistic_type = StatisticType.KR20
        if statistic_type is None:
            continue

        for column_index, instrument_hint in header_hints.items():
            if column_index >= len(row):
                continue
            raw_cell = _clean_table_cell_text(row[column_index])
            match = re.search(rf"\b({_DECIMAL})\b", raw_cell)
            if not match:
                continue
            raw_value = match.group(1)
            _append_candidate(
                file_path=file_path,
                sentence=sentence,
                statistic_type=statistic_type,
                value_raw=raw_value,
                value_normalized=_to_float(raw_value),
                subgroup_label=None,
                surrounding_text=text,
                instrument_hints=(instrument_hint,),
                comparator_hints=comparator_hints,
                method_labels=sentence_method_labels,
                candidates=candidates,
                seen=seen,
            )


def _extract_rater_reliability_coefficients(
    *,
    file_path: str,
    sentence: SentenceRecord,
    subgroup_label: str | None,
    candidates: list[StatisticCandidate],
    seen: set[tuple[object, ...]],
    instrument_hints: tuple[str, ...],
    comparator_hints: tuple[str, ...],
    sentence_method_labels: tuple[EvidenceMethodLabel, ...],
) -> None:
    text = sentence.provenance.raw_text
    for match in _RATER_RELIABILITY_SPAN_RE.finditer(text):
        clause_text = match.group(0)
        clause_lower = clause_text.lower()
        statistic_type = StatisticType.ICC
        if "weighted kappa" in clause_lower or "κw" in clause_lower:
            statistic_type = StatisticType.WEIGHTED_KAPPA
        elif "kappa" in clause_lower or "κ" in clause_text:
            statistic_type = StatisticType.KAPPA
        clause_hints = _detect_instrument_hints(clause_text) or instrument_hints
        if not clause_hints:
            continue
        for value_match in re.finditer(rf"({_DECIMAL})", clause_text):
            raw_value = value_match.group(1)
            if "." not in raw_value:
                continue
            left_window = clause_text[max(0, value_match.start() - 8) : value_match.start()].lower()
            if re.search(r"p\s*<\s*$", left_window):
                continue
            normalized = _to_float(raw_value)
            if normalized is None or normalized < -1.0 or normalized > 1.0:
                continue
            _append_candidate(
                file_path=file_path,
                sentence=sentence,
                statistic_type=statistic_type,
                value_raw=raw_value,
                value_normalized=normalized,
                subgroup_label=subgroup_label,
                surrounding_text=clause_text,
                instrument_hints=clause_hints,
                comparator_hints=comparator_hints,
                method_labels=sentence_method_labels,
                candidates=candidates,
                seen=seen,
            )


def _extract_table_rows(text: str) -> tuple[tuple[str, ...], ...]:
    rows: list[tuple[str, ...]] = []
    for row_match in re.finditer(r"<tr[^>]*>(.*?)</tr>", text, re.IGNORECASE | re.DOTALL):
        row_html = row_match.group(1)
        cells = tuple(
            cell_match.group(1)
            for cell_match in re.finditer(
                r"<t[dh][^>]*>(.*?)</t[dh]>",
                row_html,
                re.IGNORECASE | re.DOTALL,
            )
        )
        if cells:
            rows.append(cells)
    return tuple(rows)


def _table_column_instrument_hints(rows: tuple[tuple[str, ...], ...]) -> dict[int, str]:
    for row in rows:
        by_column: dict[int, str] = {}
        for index, raw_cell in enumerate(row):
            normalized_label = _normalize_table_instrument_label(_clean_table_cell_text(raw_cell))
            if normalized_label:
                by_column[index] = normalized_label
        if len(by_column) >= 2:
            return by_column
    return {}


def _clean_table_cell_text(raw_cell: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw_cell)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _normalize_table_instrument_label(value: str) -> str | None:
    cleaned = value.strip(" :;,.")
    if not cleaned:
        return None

    detected_hints = _detect_instrument_hints(cleaned)
    if detected_hints:
        return detected_hints[0]

    if re.fullmatch(r"[A-Z][A-Z0-9\-]*(?:\s+\d+(?:\.\d+)*)?", cleaned):
        return cleaned

    return None


def _extract_loa(
    *,
    file_path: str,
    sentence: SentenceRecord,
    subgroup_label: str | None,
    candidates: list[StatisticCandidate],
    seen: set[tuple[object, ...]],
    instrument_hints: tuple[str, ...],
    comparator_hints: tuple[str, ...],
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
            comparator_hints=comparator_hints,
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
    comparator_hints: tuple[str, ...],
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
            comparator_hints=comparator_hints,
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
            comparator_hints=comparator_hints,
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
    comparator_hints: tuple[str, ...],
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
        comparator_hints=comparator_hints,
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
    comparator_hints: tuple[str, ...],
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
        comparator_hints=comparator_hints,
        method_labels=sentence_method_labels,
        candidates=candidates,
        seen=seen,
    )


def _extract_internal_structure_signals(
    *,
    file_path: str,
    sentence: SentenceRecord,
    subgroup_label: str | None,
    candidates: list[StatisticCandidate],
    seen: set[tuple[object, ...]],
    instrument_hints: tuple[str, ...],
    comparator_hints: tuple[str, ...],
    sentence_method_labels: tuple[EvidenceMethodLabel, ...],
) -> None:
    text = sentence.provenance.raw_text
    if not _INTERNAL_STRUCTURE_SIGNAL_RE.search(text):
        return

    _append_candidate(
        file_path=file_path,
        sentence=sentence,
        statistic_type=StatisticType.INTERNAL_STRUCTURE_FINDING,
        value_raw=text,
        value_normalized="reported",
        subgroup_label=subgroup_label,
        surrounding_text=text,
        instrument_hints=instrument_hints,
        comparator_hints=comparator_hints,
        method_labels=sentence_method_labels,
        measurement_routes=(MeasurementPropertyRoute.STRUCTURAL_VALIDITY,),
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
    comparator_hints: tuple[str, ...],
    sentence_method_labels: tuple[EvidenceMethodLabel, ...],
) -> None:
    text = sentence.provenance.raw_text
    text_lower = text.lower()

    if "responsiveness" not in text_lower:
        return

    if _NOT_ASSESSED_RE.search(text):
        _append_candidate(
            file_path=file_path,
            sentence=sentence,
            statistic_type=StatisticType.RESPONSIVENESS_RELATED_STATISTIC,
            value_raw=text,
            value_normalized="not_assessed",
            subgroup_label=subgroup_label,
            surrounding_text=text,
            instrument_hints=instrument_hints,
            comparator_hints=comparator_hints,
            method_labels=sentence_method_labels,
            supports_direct_assessment=False,
            candidates=candidates,
            seen=seen,
        )
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
            comparator_hints=comparator_hints,
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
            comparator_hints=comparator_hints,
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
    comparator_hints: tuple[str, ...],
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
            comparator_hints=comparator_hints,
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
    comparator_hints: tuple[str, ...],
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
    if _MCID_TERM_RE.search(text_lower):
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
        comparator_hints=comparator_hints,
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
    comparator_hints: tuple[str, ...],
    method_labels: tuple[EvidenceMethodLabel, ...],
    candidates: list[StatisticCandidate],
    seen: set[tuple[object, ...]],
    evidence_source: EvidenceSourceType | None = None,
    measurement_routes: tuple[MeasurementPropertyRoute, ...] | None = None,
    supports_direct_assessment: bool | None = None,
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
    direct_assessment = (
        supports_direct_assessment
        if supports_direct_assessment is not None
        else _supports_direct_assessment(text=surrounding_text, source=source)
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
        tuple(comparator_hints),
        direct_assessment,
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
                ",".join(comparator_hints),
                str(direct_assessment),
                hypothesis_status.value if hypothesis_status else "",
            ),
            statistic_type=statistic_type,
            value_raw=normalized_raw,
            value_normalized=value_normalized,
            subgroup_label=subgroup_label,
            evidence_span_ids=(sentence.id,),
            surrounding_text=surrounding_text,
            instrument_name_hints=instrument_hints,
            comparator_instrument_hints=comparator_hints,
            evidence_source=source,
            supports_direct_assessment=direct_assessment,
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

    # MIC/MCID values are interpretability-oriented by definition.
    if statistic_type is StatisticType.MIC:
        return True

    # SEM/SDC/LoA can support measurement-error appraisal directly in current
    # studies; only classify as interpretability-only when explicitly framed
    # that way via interpretability tokens above.
    if statistic_type in (StatisticType.SEM, StatisticType.SDC, StatisticType.LOA):
        return False

    return False


def _supports_direct_assessment(*, text: str, source: EvidenceSourceType) -> bool:
    if source is not EvidenceSourceType.CURRENT_STUDY:
        return False
    text_lower = text.lower()
    if _NOT_ASSESSED_RE.search(text):
        return False
    return not any(
        token in text_lower
        for token in (
            "future studies",
            "not assessed",
            "not evaluated",
            "impossible to verify",
            "lack of a gold standard",
        )
    )


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
    elif statistic_type in (StatisticType.CRONBACH_ALPHA, StatisticType.KR20):
        routes.append(MeasurementPropertyRoute.INTERNAL_CONSISTENCY)
    elif statistic_type in (StatisticType.ICC, StatisticType.WEIGHTED_KAPPA, StatisticType.KAPPA):
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
    elif statistic_type is StatisticType.INTERNAL_STRUCTURE_FINDING:
        routes.append(MeasurementPropertyRoute.STRUCTURAL_VALIDITY)

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


def _partition_candidate_ids(
    candidates: list[StatisticCandidate],
) -> tuple[tuple[StableId, ...], tuple[StableId, ...], tuple[StableId, ...], tuple[StableId, ...]]:
    direct_ids: list[StableId] = []
    background_ids: list[StableId] = []
    interpretability_ids: list[StableId] = []
    comparator_ids: list[StableId] = []

    for candidate in candidates:
        if (
            candidate.evidence_source is EvidenceSourceType.CURRENT_STUDY
            and candidate.supports_direct_assessment
        ):
            direct_ids.append(candidate.id)
        if candidate.evidence_source is EvidenceSourceType.BACKGROUND_CITATION:
            background_ids.append(candidate.id)
        if candidate.evidence_source is EvidenceSourceType.INTERPRETABILITY_ONLY:
            interpretability_ids.append(candidate.id)
        if candidate.comparator_instrument_hints:
            comparator_ids.append(candidate.id)

    return (
        tuple(dict.fromkeys(direct_ids)),
        tuple(dict.fromkeys(background_ids)),
        tuple(dict.fromkeys(interpretability_ids)),
        tuple(dict.fromkeys(comparator_ids)),
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


def _detect_instrument_hints(text: str) -> tuple[str, ...]:
    hints: list[str] = []

    if _SIGAM_FULL_RE.search(text) or _SIGAM_ABBR_RE.search(text):
        hints.append("SIGAM")
    if _LCI5_FULL_RE.search(text) or _LCI5_ABBR_RE.search(text):
        hints.append("LCI-5")
    if _HOUGHTON_RE.search(text):
        hints.append("Houghton")
    if _ABC_FULL_RE.search(text) or _ABC_ABBR_RE.search(text):
        hints.append("ABC")
    if _GPS_FULL_RE.search(text) or _GPS_ABBR_RE.search(text):
        hints.append("GPS")
    if _TWO_MWT_FULL_RE.search(text) or _TWO_MWT_ABBR_RE.search(text):
        hints.append("2-MWT")
    if _TUG_FULL_RE.search(text) or _TUG_ABBR_RE.search(text):
        hints.append("TUG")
    if _COLD_TUG_FULL_RE.search(text) or _COLD_TUG_ABBR_RE.search(text):
        hints.append("COLD-TUG")
    if _SIX_MWT_FULL_RE.search(text) or _SIX_MWT_ABBR_RE.search(text):
        hints.append("6-MWT")
    if _QTFA_FULL_RE.search(text) or _QTFA_ABBR_RE.search(text):
        hints.append("Q-TFA")
    if _PROMIS_FULL_RE.search(text) or _PROMIS_ABBR_RE.search(text):
        hints.append("PROMIS")

    if _GENERIC_INSTRUMENT_CONTEXT_RE.search(text) or _OUTCOME_LIST_RE.search(text):
        for match in _GENERIC_INSTRUMENT_TOKEN_RE.finditer(text):
            token = match.group(1).strip()
            if token.upper() in _GENERIC_INSTRUMENT_STOPWORDS:
                continue
            hints.append(token)

    outcome_match = _OUTCOME_LIST_RE.search(text)
    if outcome_match:
        for item in _split_outcome_list_items(outcome_match.group(1)):
            if len(item) < 3:
                continue
            if any(char.isdigit() for char in item) or " " in item:
                hints.append(item)

    return tuple(dict.fromkeys(hints))


def _detect_comparator_instrument_hints(text: str) -> tuple[str, ...]:
    text_lower = text.lower()
    if not _COMPARATOR_CONTEXT_RE.search(text_lower) and "construct validity" not in text_lower:
        return ()
    hints = _detect_instrument_hints(text)
    if len(hints) <= 1:
        return ()
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


def _build_paragraph_instrument_hints(
    sentences: tuple[SentenceRecord, ...],
) -> dict[StableId, tuple[str, ...]]:
    by_paragraph: dict[StableId, list[str]] = {}
    for sentence in sentences:
        hints = _detect_instrument_hints(sentence.provenance.raw_text)
        if not hints:
            continue
        bucket = by_paragraph.setdefault(sentence.parent_paragraph_id, [])
        bucket.extend(hints)
    return {
        paragraph_id: tuple(dict.fromkeys(hints)) for paragraph_id, hints in by_paragraph.items()
    }


def _merge_instrument_hints(
    sentence_hints: tuple[str, ...],
    paragraph_hints: tuple[str, ...],
) -> tuple[str, ...]:
    # Prefer sentence-local instrument mentions to avoid leaking paragraph-level
    # co-mentioned instruments into target-specific evidence routing.
    if sentence_hints:
        return tuple(dict.fromkeys(sentence_hints))
    if paragraph_hints:
        return tuple(dict.fromkeys(paragraph_hints))
    return ()


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


def _split_outcome_list_items(raw_text: str) -> tuple[str, ...]:
    cleaned = re.sub(r"\([^)]*\)", "", raw_text)
    normalized = cleaned.replace(" and ", ",")
    items = [item.strip(" :;,.") for item in normalized.split(",")]
    filtered = [item for item in items if item]
    return tuple(dict.fromkeys(filtered))


def _extract_additional_mic_values(
    *,
    file_path: str,
    sentence: SentenceRecord,
    sentence_text: str,
    tail_start: int,
    subgroup_label: str | None,
    candidates: list[StatisticCandidate],
    seen: set[tuple[object, ...]],
    comparator_hints: tuple[str, ...],
    method_labels: tuple[EvidenceMethodLabel, ...],
) -> None:
    tail_text = sentence_text[tail_start:]
    if not tail_text:
        return

    for match in _ADDITIONAL_VALUE_PAIR_RE.finditer(tail_text):
        raw_target = match.group(1).strip(" ,.;:()")
        raw_value = match.group(2)
        normalized_target = _normalize_local_target_hint(raw_target)
        if not normalized_target:
            continue

        _append_candidate(
            file_path=file_path,
            sentence=sentence,
            statistic_type=StatisticType.MIC,
            value_raw=raw_value,
            value_normalized=_to_float(raw_value),
            subgroup_label=subgroup_label,
            surrounding_text=sentence_text,
            instrument_hints=(normalized_target,),
            comparator_hints=comparator_hints,
            method_labels=method_labels,
            candidates=candidates,
            seen=seen,
        )


def _extract_mic_value_pairs_without_inline_numeric(
    *,
    file_path: str,
    sentence: SentenceRecord,
    sentence_text: str,
    subgroup_label: str | None,
    candidates: list[StatisticCandidate],
    seen: set[tuple[object, ...]],
    comparator_hints: tuple[str, ...],
    method_labels: tuple[EvidenceMethodLabel, ...],
) -> None:
    token_match = re.search(r"\b(?:MIC|MCID|MID)\b", sentence_text, re.IGNORECASE)
    if not token_match:
        return

    tail_text = sentence_text[token_match.end() :]
    if not tail_text:
        return

    for match in _MIC_VALUE_PAIR_RE.finditer(tail_text):
        raw_target = match.group(1).strip(" ,.;:()")
        raw_value = match.group(2)
        normalized_target = _normalize_local_target_hint(raw_target)
        if not normalized_target:
            continue

        _append_candidate(
            file_path=file_path,
            sentence=sentence,
            statistic_type=StatisticType.MIC,
            value_raw=raw_value,
            value_normalized=_to_float(raw_value),
            subgroup_label=subgroup_label,
            surrounding_text=sentence_text,
            instrument_hints=(normalized_target,),
            comparator_hints=comparator_hints,
            method_labels=method_labels,
            candidates=candidates,
            seen=seen,
        )


def _detect_local_target_hints_for_value(*, text: str, value_start: int) -> tuple[str, ...]:
    left_window = text[max(0, value_start - 90) : value_start]
    match = _LOCAL_TARGET_VALUE_RE.search(left_window)
    if not match:
        return ()

    raw_target = match.group(1).strip(" ,.;:()")
    if not raw_target:
        return ()

    lowered = raw_target.lower()
    if lowered in {"mic", "mcid", "mid", "difference"}:
        return ()

    normalized_target = _normalize_local_target_hint(raw_target)
    if not normalized_target:
        return ()
    return (normalized_target,)


def _normalize_local_target_hint(raw_target: str) -> str:
    text = raw_target.strip()
    if not text:
        return ""
    if _TWO_MWT_FULL_RE.search(text) or _TWO_MWT_ABBR_RE.search(text):
        return "2-MWT"
    if _GPS_FULL_RE.search(text) or _GPS_ABBR_RE.search(text):
        return "GPS"
    return text
