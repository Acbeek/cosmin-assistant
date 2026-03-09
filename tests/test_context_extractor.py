"""Fixture-based tests for first-pass study/instrument context extraction."""

from __future__ import annotations

from pathlib import Path

from cosmin_assistant.extract import (
    FieldDetectionStatus,
    extract_context_from_markdown_file,
)

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "markdown"


def _fixture(name: str) -> Path:
    return _FIXTURE_DIR / name


def test_straightforward_context_extraction() -> None:
    result = extract_context_from_markdown_file(_fixture("context_straightforward.md"))

    study = result.study_contexts[0]
    instrument = result.instrument_contexts[0]

    assert instrument.instrument_name.status is FieldDetectionStatus.DETECTED
    assert instrument.instrument_name.candidates[0].normalized_value == "PROM-X"
    assert instrument.instrument_version.candidates[0].normalized_value == "2.1"
    assert instrument.subscale.candidates[0].normalized_value == "Mobility"
    assert study.construct_field.candidates[0].normalized_value == "Physical Functioning"
    assert (
        study.target_population.candidates[0].normalized_value == "Adults with knee osteoarthritis"
    )
    assert study.language.candidates[0].normalized_value == "English"
    assert study.country.candidates[0].normalized_value == "Netherlands"
    assert study.study_design.candidates[0].normalized_value == "cross_sectional_validation_study"
    assert study.sample_sizes.candidates[0].normalized_value == 120
    assert study.measurement_properties_mentioned.candidates[0].normalized_value == (
        "hypotheses_testing_for_construct_validity",
        "reliability",
        "responsiveness",
    )


def test_ambiguous_extraction_preserves_multiple_candidates() -> None:
    result = extract_context_from_markdown_file(_fixture("context_ambiguous.md"))

    study = result.study_contexts[0]
    instrument = result.instrument_contexts[0]

    assert instrument.instrument_name.status is FieldDetectionStatus.AMBIGUOUS
    assert {candidate.normalized_value for candidate in instrument.instrument_name.candidates} == {
        "PROM-A",
        "PROM-B",
    }

    assert study.language.status is FieldDetectionStatus.AMBIGUOUS
    assert {candidate.normalized_value for candidate in study.language.candidates} == {
        "English",
        "Dutch",
    }

    assert study.country.status is FieldDetectionStatus.AMBIGUOUS
    assert {candidate.normalized_value for candidate in study.country.candidates} == {
        "Netherlands",
        "Belgium",
    }

    assert study.sample_sizes.status is FieldDetectionStatus.AMBIGUOUS
    assert {candidate.normalized_value for candidate in study.sample_sizes.candidates} == {80, 92}


def test_missing_fields_distinguish_not_reported_and_not_detected() -> None:
    result = extract_context_from_markdown_file(_fixture("context_missing_fields.md"))

    study = result.study_contexts[0]
    instrument = result.instrument_contexts[0]

    assert instrument.instrument_name.status is FieldDetectionStatus.NOT_REPORTED
    assert study.language.status is FieldDetectionStatus.NOT_REPORTED
    assert study.sample_sizes.status is FieldDetectionStatus.NOT_REPORTED

    assert instrument.instrument_version.status is FieldDetectionStatus.NOT_DETECTED
    assert instrument.subscale.status is FieldDetectionStatus.NOT_DETECTED
    assert study.country.status is FieldDetectionStatus.NOT_DETECTED
    assert study.measurement_properties_mentioned.status is FieldDetectionStatus.NOT_DETECTED


def test_multiple_subsamples_can_coexist_in_single_article_context() -> None:
    result = extract_context_from_markdown_file(_fixture("context_multiple_subsamples.md"))

    study = result.study_contexts[0]

    assert len(study.subsamples) == 2
    assert {subsample.label_normalized for subsample in study.subsamples} == {
        "a",
        "b",
    }
    assert {subsample.sample_size_normalized for subsample in study.subsamples} == {60, 90}


def test_extraction_is_deterministic_for_same_input() -> None:
    first = extract_context_from_markdown_file(_fixture("context_straightforward.md"))
    second = extract_context_from_markdown_file(_fixture("context_straightforward.md"))

    assert first == second
