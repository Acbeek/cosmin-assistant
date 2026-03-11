"""Tests for thin batch orchestration scaffold built on frozen single-paper logic."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import cosmin_assistant.cli.batch_app as batch_app
from cosmin_assistant.cli.batch_app import (
    _allocate_unique_output_dir_name,
    app,
    discover_markdown_articles,
    run_batch_assessment,
)
from cosmin_assistant.cli.pipeline import run_provisional_assessment
from cosmin_assistant.models import ProfileType
from cosmin_assistant.tables import export_run_outputs

_FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "markdown"
_CORPUS_ROOT = Path(__file__).resolve().parent / "fixtures" / "corpus"
_THREE_PAPER_FIXTURES = (
    "awad_pbom_validation.md",
    "azadinia_validation_prom.md",
    "potter_longitudinal_prom.md",
)
_KEY_ACTIVE_STATUSES = {
    "direct_current_study_evidence",
    "measurement_error_support_only",
    "interpretability_only",
}


def test_discover_markdown_articles_scans_directory_and_sorts(tmp_path: Path) -> None:
    (tmp_path / "zeta.md").write_text("# zeta", encoding="utf-8")
    (tmp_path / "alpha.md").write_text("# alpha", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "beta.md").write_text("# beta", encoding="utf-8")

    non_recursive = discover_markdown_articles(input_dir=tmp_path, recursive=False)
    recursive = discover_markdown_articles(input_dir=tmp_path, recursive=True)

    assert [path.name for path in non_recursive] == ["alpha.md", "zeta.md"]
    assert [path.name for path in recursive] == ["alpha.md", "beta.md", "zeta.md"]


def test_batch_cli_writes_per_article_outputs_and_summary(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "paper_a.md").write_text(
        (_FIXTURE_ROOT / "e2e_prom_article.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    nested = input_dir / "nested"
    nested.mkdir()
    (nested / "paper_b.md").write_text(
        (_FIXTURE_ROOT / "holdout_generic_validation.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    out_dir = tmp_path / "batch_out"
    runner = CliRunner()
    invocation = runner.invoke(
        app,
        [str(input_dir), "--profile", "prom", "--out", str(out_dir), "--recursive"],
    )

    assert invocation.exit_code == 0, invocation.output

    summary_csv = out_dir / "batch_summary.csv"
    summary_json = out_dir / "batch_summary.json"
    assert summary_csv.exists()
    assert summary_json.exists()

    with summary_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 2
    for row in rows:
        assert row["article_name"]
        assert row["article_path"]
        assert row["target_instruments"]
        assert row["study_intent"]
        assert row["key_active_properties"]
        assert row["review_status"] == "provisional"
        assert row["run_status"] == "success"
        assert row["error_message"] == ""

        output_dir = Path(row["output_dir"])
        assert output_dir.exists()
        manifest_path = output_dir / "run_manifest.json"
        assert manifest_path.exists()
        assert (output_dir / "review_state.json").exists()

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifact_prefix = manifest["artifact_prefix"]
        assert (output_dir / f"{artifact_prefix}__run_manifest.json").exists()
        assert (output_dir / f"{artifact_prefix}__measurement_property_results.json").exists()
        assert (output_dir / f"{artifact_prefix}__synthesis.json").exists()


def test_batch_scaffold_keeps_single_article_outputs_identical(tmp_path: Path) -> None:
    input_dir = tmp_path / "input_single"
    input_dir.mkdir()
    article_path = input_dir / "paper.md"
    article_path.write_text(
        (_FIXTURE_ROOT / "e2e_prom_article.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    batch_out = tmp_path / "batch_single"
    outputs = run_batch_assessment(
        input_dir=input_dir,
        out_dir=batch_out,
        profile_type=ProfileType.PROM,
        recursive=False,
    )

    summary_payload = json.loads(Path(outputs["batch_summary_json"]).read_text(encoding="utf-8"))
    assert isinstance(summary_payload, list)
    assert len(summary_payload) == 1
    batch_article_out = Path(summary_payload[0]["output_dir"])

    single_out = tmp_path / "single_out"
    run = run_provisional_assessment(article_path=article_path, profile_type=ProfileType.PROM)
    export_run_outputs(run=run, out_dir=single_out)

    for file_name in (
        "evidence.json",
        "rob_assessment.json",
        "measurement_property_results.json",
        "synthesis.json",
        "grade.json",
    ):
        batch_payload = json.loads((batch_article_out / file_name).read_text(encoding="utf-8"))
        single_payload = json.loads((single_out / file_name).read_text(encoding="utf-8"))
        assert batch_payload == single_payload


def test_batch_three_paper_semantics_match_single_runs(tmp_path: Path) -> None:
    input_dir = _prepare_input_dir(tmp_path=tmp_path, file_names=_THREE_PAPER_FIXTURES)
    batch_out = tmp_path / "batch_three"
    outputs = run_batch_assessment(
        input_dir=input_dir,
        out_dir=batch_out,
        profile_type=ProfileType.PROM,
        recursive=False,
    )
    assert outputs["articles_failed"] == "0"

    summary_payload = json.loads(Path(outputs["batch_summary_json"]).read_text(encoding="utf-8"))
    by_article = {row["article_name"]: row for row in summary_payload}

    for file_name in _THREE_PAPER_FIXTURES:
        article_path = input_dir / file_name
        single_run = run_provisional_assessment(article_path=article_path, profile_type="prom")
        single_semantics = _semantic_snapshot_from_run(single_run)

        batch_row = by_article[file_name]
        batch_semantics = _semantic_snapshot_from_output_dir(Path(batch_row["output_dir"]))
        assert batch_semantics == single_semantics

        assert batch_row["target_instruments"] == "; ".join(single_semantics["target_instruments"])
        assert batch_row["study_intent"] == single_semantics["study_intent"]
        assert batch_row["key_active_properties"] == "; ".join(
            single_semantics["key_active_properties"]
        )
        assert batch_row["review_status"] == "provisional"
        assert batch_row["run_status"] == "success"
        assert batch_row["error_message"] == ""


def test_batch_summary_json_matches_golden_semantics_for_three_paper_fixture(
    tmp_path: Path,
) -> None:
    input_dir = _prepare_input_dir(tmp_path=tmp_path, file_names=_THREE_PAPER_FIXTURES)
    batch_out = tmp_path / "batch_golden"
    outputs = run_batch_assessment(
        input_dir=input_dir,
        out_dir=batch_out,
        profile_type=ProfileType.PROM,
        recursive=False,
    )
    assert outputs["articles_failed"] == "0"

    summary_payload = json.loads(Path(outputs["batch_summary_json"]).read_text(encoding="utf-8"))
    actual = sorted(
        (_normalize_summary_row_for_semantics(row) for row in summary_payload),
        key=lambda row: str(row["article_name"]),
    )

    golden_path = _CORPUS_ROOT / "batch_summary_golden.json"
    expected = sorted(
        json.loads(golden_path.read_text(encoding="utf-8")),
        key=lambda row: str(row["article_name"]),
    )

    assert actual == expected
    assert all(Path(row["article_path"]).is_absolute() for row in summary_payload)
    assert all(Path(row["output_dir"]).is_absolute() for row in summary_payload)


def test_batch_assessment_continues_on_error_and_writes_failure_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "input_failure"
    input_dir.mkdir()
    (input_dir / "a_bad.md").write_text("# bad fixture", encoding="utf-8")
    (input_dir / "b_good.md").write_text(
        (_FIXTURE_ROOT / "e2e_prom_article.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    original = batch_app.run_provisional_assessment  # type: ignore[attr-defined]

    def _patched_run(*, article_path: str | Path, profile_type: ProfileType | str) -> Any:
        if Path(article_path).name == "a_bad.md":
            raise ValueError("synthetic failure for testing")
        return original(article_path=article_path, profile_type=profile_type)

    monkeypatch.setattr("cosmin_assistant.cli.batch_app.run_provisional_assessment", _patched_run)

    out_dir = tmp_path / "batch_fail_continue"
    outputs = run_batch_assessment(
        input_dir=input_dir,
        out_dir=out_dir,
        profile_type=ProfileType.PROM,
        recursive=False,
        continue_on_error=True,
    )

    assert outputs["articles_discovered"] == "2"
    assert outputs["articles_processed"] == "2"
    assert outputs["articles_succeeded"] == "1"
    assert outputs["articles_failed"] == "1"
    assert outputs["exit_code"] == "1"

    summary = json.loads((out_dir / "batch_summary.json").read_text(encoding="utf-8"))
    by_name = {row["article_name"]: row for row in summary}

    bad_row = by_name["a_bad.md"]
    assert bad_row["run_status"] == "failed"
    assert bad_row["review_status"] == "not_generated"
    assert "synthetic failure for testing" in bad_row["error_message"]
    bad_out = Path(bad_row["output_dir"])
    assert (bad_out / "batch_error.json").exists()
    assert not (bad_out / "evidence.json").exists()

    good_row = by_name["b_good.md"]
    assert good_row["run_status"] == "success"
    assert good_row["review_status"] == "provisional"
    good_out = Path(good_row["output_dir"])
    assert (good_out / "evidence.json").exists()
    assert not (good_out / "batch_error.json").exists()


def test_batch_assessment_fail_fast_stops_after_first_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "input_fail_fast"
    input_dir.mkdir()
    (input_dir / "a_bad.md").write_text("# bad fixture", encoding="utf-8")
    (input_dir / "b_good.md").write_text(
        (_FIXTURE_ROOT / "e2e_prom_article.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    original = batch_app.run_provisional_assessment  # type: ignore[attr-defined]

    def _patched_run(*, article_path: str | Path, profile_type: ProfileType | str) -> Any:
        if Path(article_path).name == "a_bad.md":
            raise ValueError("synthetic failure for testing")
        return original(article_path=article_path, profile_type=profile_type)

    monkeypatch.setattr("cosmin_assistant.cli.batch_app.run_provisional_assessment", _patched_run)

    out_dir = tmp_path / "batch_fail_fast"
    outputs = run_batch_assessment(
        input_dir=input_dir,
        out_dir=out_dir,
        profile_type=ProfileType.PROM,
        recursive=False,
        continue_on_error=False,
    )

    assert outputs["articles_discovered"] == "2"
    assert outputs["articles_processed"] == "1"
    assert outputs["articles_succeeded"] == "0"
    assert outputs["articles_failed"] == "1"
    assert outputs["exit_code"] == "1"

    summary = json.loads((out_dir / "batch_summary.json").read_text(encoding="utf-8"))
    assert len(summary) == 1
    assert summary[0]["article_name"] == "a_bad.md"
    assert summary[0]["run_status"] == "failed"


def test_batch_cli_returns_exit_code_1_when_any_article_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "cli_failure_input"
    input_dir.mkdir()
    (input_dir / "a_bad.md").write_text("# bad fixture", encoding="utf-8")
    (input_dir / "b_good.md").write_text(
        (_FIXTURE_ROOT / "e2e_prom_article.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    out_dir = tmp_path / "cli_failure_out"

    original = batch_app.run_provisional_assessment  # type: ignore[attr-defined]

    def _patched_run(*, article_path: str | Path, profile_type: ProfileType | str) -> Any:
        if Path(article_path).name == "a_bad.md":
            raise ValueError("synthetic failure for testing")
        return original(article_path=article_path, profile_type=profile_type)

    monkeypatch.setattr("cosmin_assistant.cli.batch_app.run_provisional_assessment", _patched_run)

    runner = CliRunner()
    invocation = runner.invoke(
        app,
        [str(input_dir), "--profile", "prom", "--out", str(out_dir), "--no-recursive"],
    )
    assert invocation.exit_code == 1

    summary = json.loads((out_dir / "batch_summary.json").read_text(encoding="utf-8"))
    assert len(summary) == 2
    assert any(row["run_status"] == "failed" for row in summary)
    assert any(row["run_status"] == "success" for row in summary)


def test_allocate_unique_output_dir_name_is_collision_safe_and_deterministic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _constant_slug(*, article_path: Path, input_root: Path) -> str:
        _ = article_path
        _ = input_root
        return "same_name"

    monkeypatch.setattr(batch_app, "_article_output_dir_name", _constant_slug)
    used_names: set[str] = set()
    input_root = tmp_path / "input_root"
    input_root.mkdir()

    first = _allocate_unique_output_dir_name(
        article_path=input_root / "a.md",
        input_root=input_root,
        used_names=used_names,
    )
    second = _allocate_unique_output_dir_name(
        article_path=input_root / "b.md",
        input_root=input_root,
        used_names=used_names,
    )
    third = _allocate_unique_output_dir_name(
        article_path=input_root / "c.md",
        input_root=input_root,
        used_names=used_names,
    )

    assert first == "same_name"
    assert second == "same_name__dup01"
    assert third == "same_name__dup02"


def _prepare_input_dir(*, tmp_path: Path, file_names: tuple[str, ...]) -> Path:
    input_dir = tmp_path / "batch_input"
    input_dir.mkdir()
    for file_name in file_names:
        (input_dir / file_name).write_text(
            (_FIXTURE_ROOT / file_name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    return input_dir


def _semantic_snapshot_from_run(run: Any) -> dict[str, Any]:
    instrument_name_by_id = {
        context.instrument_id: (_first_name(context) or context.instrument_id)
        for context in run.context_extraction.instrument_contexts
    }
    target_instruments = sorted(
        {
            _first_name(context) or "unknown"
            for context in run.context_extraction.instrument_contexts
            if context.instrument_role.value
            in {"target_under_appraisal", "co_primary_outcome_instrument"}
        }
    )
    if not target_instruments and run.context_extraction.target_instrument_id:
        target_instruments = [
            instrument_name_by_id.get(run.context_extraction.target_instrument_id, "unknown")
        ]

    key_active_properties = sorted(
        {
            (
                f"{instrument_name_by_id.get(result.instrument_id, result.instrument_id)}:"
                f"{result.measurement_property}[{result.activation_status.value}]"
            )
            for result in run.measurement_property_results
            if result.activation_status.value in _KEY_ACTIVE_STATUSES
        }
    )

    measurement_semantics = sorted(
        (
            instrument_name_by_id.get(result.instrument_id, result.instrument_id),
            result.measurement_property,
            result.activation_status.value,
            result.computed_rating.value,
            result.uncertainty_status.value,
            result.reviewer_decision_status.value,
        )
        for result in run.measurement_property_results
    )
    synthesis_semantics = sorted(
        (
            result.instrument_name,
            result.measurement_property,
            result.activation_status.value,
            result.summary_rating.value,
            result.total_sample_size,
            result.inconsistent_findings,
        )
        for result in run.synthesis_results
    )
    grade_semantics = sorted(
        (
            result.measurement_property,
            result.activation_status.value,
            result.grade_executed,
            result.final_certainty.value,
            result.total_sample_size,
            result.total_downgrade_steps,
        )
        for result in run.grade_results
    )

    return {
        "target_instruments": target_instruments,
        "study_intent": run.context_extraction.study_contexts[0].study_intent.value,
        "key_active_properties": key_active_properties,
        "review_status": "provisional",
        "measurement_semantics": measurement_semantics,
        "synthesis_semantics": synthesis_semantics,
        "grade_semantics": grade_semantics,
    }


def _semantic_snapshot_from_output_dir(out_dir: Path) -> dict[str, Any]:
    evidence = json.loads((out_dir / "evidence.json").read_text(encoding="utf-8"))
    measurement = json.loads(
        (out_dir / "measurement_property_results.json").read_text(encoding="utf-8")
    )
    synthesis = json.loads((out_dir / "synthesis.json").read_text(encoding="utf-8"))
    grade = json.loads((out_dir / "grade.json").read_text(encoding="utf-8"))
    review_state = json.loads((out_dir / "review_state.json").read_text(encoding="utf-8"))

    contexts = evidence["context_extraction"]["instrument_contexts"]
    instrument_name_by_id = {
        context["instrument_id"]: (_first_name_from_dict(context) or context["instrument_id"])
        for context in contexts
    }
    target_instruments = sorted(
        {
            _first_name_from_dict(context) or "unknown"
            for context in contexts
            if context.get("instrument_role")
            in {"target_under_appraisal", "co_primary_outcome_instrument"}
        }
    )
    target_instrument_id = evidence["context_extraction"].get("target_instrument_id")
    if not target_instruments and target_instrument_id:
        target_instruments = [instrument_name_by_id.get(target_instrument_id, "unknown")]

    key_active_properties = sorted(
        {
            (
                f"{instrument_name_by_id.get(item['instrument_id'], item['instrument_id'])}:"
                f"{item['measurement_property']}[{item['activation_status']}]"
            )
            for item in measurement
            if item["activation_status"] in _KEY_ACTIVE_STATUSES
        }
    )
    measurement_semantics = sorted(
        (
            instrument_name_by_id.get(item["instrument_id"], item["instrument_id"]),
            item["measurement_property"],
            item["activation_status"],
            item["computed_rating"],
            item["uncertainty_status"],
            item["reviewer_decision_status"],
        )
        for item in measurement
    )
    synthesis_semantics = sorted(
        (
            item["instrument_name"],
            item["measurement_property"],
            item["activation_status"],
            item["summary_rating"],
            item["total_sample_size"],
            bool(item["inconsistent_findings"]),
        )
        for item in synthesis
    )
    grade_semantics = sorted(
        (
            item["measurement_property"],
            item["activation_status"],
            bool(item["grade_executed"]),
            item["final_certainty"],
            item["total_sample_size"],
            item["total_downgrade_steps"],
        )
        for item in grade
    )

    return {
        "target_instruments": target_instruments,
        "study_intent": evidence["context_extraction"]["study_contexts"][0]["study_intent"],
        "key_active_properties": key_active_properties,
        "review_status": review_state["review_status"],
        "measurement_semantics": measurement_semantics,
        "synthesis_semantics": synthesis_semantics,
        "grade_semantics": grade_semantics,
    }


def _first_name(context: Any) -> str | None:
    candidates = context.instrument_name.candidates
    if not candidates:
        return None
    value = candidates[0].normalized_value
    if isinstance(value, str):
        return value
    return None


def _first_name_from_dict(context: dict[str, Any]) -> str | None:
    candidates = context.get("instrument_name", {}).get("candidates", [])
    if not candidates:
        return None
    value = candidates[0].get("normalized_value")
    if isinstance(value, str):
        return value
    return None


def _normalize_summary_row_for_semantics(row: dict[str, Any]) -> dict[str, str]:
    return {
        "article_name": str(row["article_name"]),
        "target_instruments": str(row["target_instruments"]),
        "study_intent": str(row["study_intent"]),
        "key_active_properties": str(row["key_active_properties"]),
        "review_status": str(row["review_status"]),
        "run_status": str(row["run_status"]),
        "error_message": str(row["error_message"]),
    }
