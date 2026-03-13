"""End-to-end CLI test for provisional COSMIN assessment pipeline."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from typer.testing import CliRunner

from cosmin_assistant.cli.app import app

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "markdown" / "e2e_prom_article.md"
_BOX1_ELIGIBLE_FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "markdown" / "nonsci_hafner2022.md"
)
_NON_DEVELOPMENT_PROM_FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "markdown" / "sci_hafner2017.md"
)


def test_cli_runs_end_to_end_and_exports_required_artifacts(tmp_path: Path) -> None:
    out_dir = tmp_path / "results"
    runner = CliRunner()

    invocation = runner.invoke(
        app,
        [str(_FIXTURE_PATH), "--profile", "prom", "--out", str(out_dir)],
    )

    assert invocation.exit_code == 0, invocation.output

    expected_paths = {
        "evidence.json": out_dir / "evidence.json",
        "rob_assessment.json": out_dir / "rob_assessment.json",
        "measurement_property_results.json": out_dir / "measurement_property_results.json",
        "synthesis.json": out_dir / "synthesis.json",
        "grade.json": out_dir / "grade.json",
        "summary_report.md": out_dir / "summary_report.md",
        "per_study_results.csv": out_dir / "per_study_results.csv",
        "summary_report.docx": out_dir / "summary_report.docx",
        "run_manifest.json": out_dir / "run_manifest.json",
    }

    for path in expected_paths.values():
        assert path.exists()
        assert path.stat().st_size > 0

    for json_name in (
        "evidence.json",
        "rob_assessment.json",
        "measurement_property_results.json",
        "synthesis.json",
        "grade.json",
    ):
        payload = json.loads(expected_paths[json_name].read_text(encoding="utf-8"))
        assert payload is not None

    markdown_report = expected_paths["summary_report.md"].read_text(encoding="utf-8")
    assert "# COSMIN Assistant Provisional Summary" in markdown_report
    assert "Measurement Property Ratings" in markdown_report

    manifest = json.loads(expected_paths["run_manifest.json"].read_text(encoding="utf-8"))
    assert manifest["source_article_path"].endswith("e2e_prom_article.md")
    assert manifest["source_article_hash"]
    assert manifest["profile"] == "prom"
    assert manifest["python_version"]

    with expected_paths["per_study_results.csv"].open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert "measurement_property" in rows[0]

    assert "summary_report_docx:" in invocation.output


def test_cli_fails_when_reusing_output_dir_with_changed_source_hash(tmp_path: Path) -> None:
    article_path = tmp_path / "article.md"
    article_path.write_text(
        "# Study\nInstrument name: PROM-HASH.\nCronbach's alpha = 0.80.\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "results"
    runner = CliRunner()

    first = runner.invoke(
        app,
        [str(article_path), "--profile", "prom", "--out", str(out_dir)],
    )
    assert first.exit_code == 0, first.output

    article_path.write_text(
        "# Study\nInstrument name: PROM-HASH.\nCronbach's alpha = 0.75.\n",
        encoding="utf-8",
    )
    second = runner.invoke(
        app,
        [str(article_path), "--profile", "prom", "--out", str(out_dir)],
    )

    assert second.exit_code != 0
    assert "stale artifacts" in second.output.lower()


def test_cli_exposes_box2_content_validity_as_manual_reviewer_required_path(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "results_box2"
    runner = CliRunner()

    invocation = runner.invoke(
        app,
        [str(_FIXTURE_PATH), "--profile", "prom", "--out", str(out_dir)],
    )
    assert invocation.exit_code == 0, invocation.output

    rob_payload = json.loads((out_dir / "rob_assessment.json").read_text(encoding="utf-8"))
    assert isinstance(rob_payload, list)
    box2_bundles = [
        bundle
        for bundle in rob_payload
        if bundle.get("box_assessment", {}).get("cosmin_box") == "box_2_content_validity"
    ]
    assert box2_bundles

    box2 = box2_bundles[0]
    box_assessment = box2["box_assessment"]
    assert box_assessment["measurement_property"] == "content_validity"
    assert box_assessment["uncertainty_status"] == "reviewer_required"
    assert box_assessment["reviewer_decision_status"] == "pending"

    item_assessments = box2["item_assessments"]
    assert item_assessments
    assert all(item["item_rating"] == "doubtful" for item in item_assessments)
    assert all(item["uncertainty_status"] == "reviewer_required" for item in item_assessments)
    assert all(item["reviewer_decision_status"] == "pending" for item in item_assessments)

    measurement_payload = json.loads(
        (out_dir / "measurement_property_results.json").read_text(encoding="utf-8")
    )
    assert isinstance(measurement_payload, list)
    assert not any(
        item["measurement_property"] == "content_validity" for item in measurement_payload
    )


def test_cli_exposes_box1_prom_development_only_for_eligible_manual_path(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "results_box1_eligible"
    runner = CliRunner()

    invocation = runner.invoke(
        app,
        [str(_BOX1_ELIGIBLE_FIXTURE_PATH), "--profile", "prom", "--out", str(out_dir)],
    )
    assert invocation.exit_code == 0, invocation.output

    rob_payload = json.loads((out_dir / "rob_assessment.json").read_text(encoding="utf-8"))
    assert isinstance(rob_payload, list)

    box1_bundles = [
        bundle
        for bundle in rob_payload
        if bundle.get("box_assessment", {}).get("cosmin_box") == "box_1_prom_development"
    ]
    assert box1_bundles

    box1 = box1_bundles[0]
    box_assessment = box1["box_assessment"]
    assert box_assessment["measurement_property"] == "prom_development"
    assert box_assessment["uncertainty_status"] == "reviewer_required"
    assert box_assessment["reviewer_decision_status"] == "pending"

    item_assessments = box1["item_assessments"]
    assert item_assessments
    assert all(item["item_rating"] == "doubtful" for item in item_assessments)
    assert all(item["uncertainty_status"] == "reviewer_required" for item in item_assessments)
    assert all(item["reviewer_decision_status"] == "pending" for item in item_assessments)


def test_cli_does_not_emit_box1_placeholder_for_non_development_prom_paper(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "results_box1_non_development"
    runner = CliRunner()

    invocation = runner.invoke(
        app,
        [str(_NON_DEVELOPMENT_PROM_FIXTURE_PATH), "--profile", "prom", "--out", str(out_dir)],
    )
    assert invocation.exit_code == 0, invocation.output

    rob_payload = json.loads((out_dir / "rob_assessment.json").read_text(encoding="utf-8"))
    assert isinstance(rob_payload, list)
    assert not any(
        bundle.get("box_assessment", {}).get("cosmin_box") == "box_1_prom_development"
        for bundle in rob_payload
    )
