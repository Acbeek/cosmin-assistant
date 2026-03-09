"""Tests for statistics candidate extraction with provenance preservation."""

from __future__ import annotations

from pathlib import Path

from cosmin_assistant.extract import (
    StatisticType,
    extract_statistics_from_markdown_file,
)

_FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "markdown" / "statistics_noisy_patterns.md"
)


def test_all_core_statistic_types_can_be_extracted() -> None:
    result = extract_statistics_from_markdown_file(_FIXTURE_PATH)
    found_types = {candidate.statistic_type for candidate in result.candidates}

    expected_types = {
        StatisticType.CRONBACH_ALPHA,
        StatisticType.ICC,
        StatisticType.WEIGHTED_KAPPA,
        StatisticType.SEM,
        StatisticType.SDC,
        StatisticType.LOA,
        StatisticType.MIC,
        StatisticType.CFI,
        StatisticType.TLI,
        StatisticType.RMSEA,
        StatisticType.SRMR,
        StatisticType.AUC,
        StatisticType.CORRELATION,
        StatisticType.DIF_FINDING,
        StatisticType.MEASUREMENT_INVARIANCE_FINDING,
        StatisticType.KNOWN_GROUPS_OR_COMPARATOR_RESULT,
        StatisticType.RESPONSIVENESS_RELATED_STATISTIC,
    }

    assert expected_types.issubset(found_types)


def test_multiple_values_and_subgroup_specific_values_are_preserved() -> None:
    result = extract_statistics_from_markdown_file(_FIXTURE_PATH)

    icc_candidates = [
        candidate
        for candidate in result.candidates
        if candidate.statistic_type is StatisticType.ICC
    ]

    assert len(icc_candidates) >= 2
    assert {candidate.subgroup_label for candidate in icc_candidates} >= {"men", "women"}


def test_raw_and_normalized_statistic_payloads_are_retained() -> None:
    result = extract_statistics_from_markdown_file(_FIXTURE_PATH)

    assert all(candidate.value_raw for candidate in result.candidates)
    assert all(candidate.surrounding_text for candidate in result.candidates)
    assert all(candidate.evidence_span_ids for candidate in result.candidates)

    loa = next(
        candidate
        for candidate in result.candidates
        if candidate.statistic_type is StatisticType.LOA
    )
    assert loa.value_normalized == (-3.2, 4.1)


def test_same_sentence_values_can_have_different_subgroup_labels() -> None:
    result = extract_statistics_from_markdown_file(_FIXTURE_PATH)

    alpha_candidates = [
        candidate
        for candidate in result.candidates
        if candidate.statistic_type is StatisticType.CRONBACH_ALPHA
    ]

    by_raw = {candidate.value_raw: candidate.subgroup_label for candidate in alpha_candidates}
    assert by_raw["0.91"] is None
    assert by_raw["0.88"] == "women"


def test_no_threshold_judgments_are_applied_in_statistics_layer() -> None:
    result = extract_statistics_from_markdown_file(_FIXTURE_PATH)

    for candidate in result.candidates:
        payload = candidate.model_dump()
        assert "judgment" not in payload
        assert "threshold" not in payload


def test_noisy_reporting_styles_are_handled() -> None:
    result = extract_statistics_from_markdown_file(_FIXTURE_PATH)

    cronbach_candidates = [
        candidate
        for candidate in result.candidates
        if candidate.statistic_type is StatisticType.CRONBACH_ALPHA
    ]
    assert len(cronbach_candidates) >= 2

    dif_values = {
        candidate.value_normalized
        for candidate in result.candidates
        if candidate.statistic_type is StatisticType.DIF_FINDING
    }
    assert dif_values >= {"no_dif", "dif_present"}

    responsiveness_values = [
        candidate.value_normalized
        for candidate in result.candidates
        if candidate.statistic_type is StatisticType.RESPONSIVENESS_RELATED_STATISTIC
    ]
    assert 0.83 in responsiveness_values
    assert 0.79 in responsiveness_values


def test_statistics_extraction_is_deterministic() -> None:
    first = extract_statistics_from_markdown_file(_FIXTURE_PATH)
    second = extract_statistics_from_markdown_file(_FIXTURE_PATH)

    assert first == second
