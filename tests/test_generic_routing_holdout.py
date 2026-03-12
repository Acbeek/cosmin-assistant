"""Hold-out regression tests for generic target/comparator/type routing rules."""

from __future__ import annotations

from pathlib import Path

from cosmin_assistant.cli.pipeline import run_provisional_assessment
from cosmin_assistant.extract import extract_context_from_markdown_file
from cosmin_assistant.models.enums import InstrumentType

_FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "markdown" / "holdout_generic_validation.md"
)


def test_holdout_generic_target_comparator_and_type_rationales() -> None:
    context = extract_context_from_markdown_file(_FIXTURE_PATH)
    by_name = {
        str(item.instrument_name.candidates[0].normalized_value): item
        for item in context.instrument_contexts
        if item.instrument_name.candidates
    }

    assert "MOBQ-12" in by_name
    assert "FAST-WALK" in by_name
    assert "BAL-INDEX" in by_name

    target = by_name["MOBQ-12"]
    assert context.target_instrument_id == target.instrument_id
    assert target.instrument_type is InstrumentType.PROM
    assert target.instrument_type_rationale
    assert target.instrument_type_evidence_span_ids
    assert target.role_rationale
    assert target.role_evidence_span_ids

    comparator_ids = set(context.comparator_instrument_ids)
    assert by_name["FAST-WALK"].instrument_id in comparator_ids
    assert by_name["BAL-INDEX"].instrument_id in comparator_ids
    assert by_name["FAST-WALK"].instrument_type is InstrumentType.PERFORMANCE_TEST
    assert by_name["FAST-WALK"].role_rationale
    assert by_name["FAST-WALK"].role_evidence_span_ids


def test_holdout_pipeline_keeps_synthesis_on_target_instrument() -> None:
    run = run_provisional_assessment(article_path=_FIXTURE_PATH, profile_type="prom")
    assert run.synthesis_results
    assert all(entry.instrument_name == "MOBQ-12" for entry in run.synthesis_results)
