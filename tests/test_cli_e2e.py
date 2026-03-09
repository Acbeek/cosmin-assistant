"""End-to-end CLI test for provisional COSMIN assessment pipeline."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from typer.testing import CliRunner

from cosmin_assistant.cli.app import app

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "markdown" / "e2e_prom_article.md"


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

    with expected_paths["per_study_results.csv"].open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert "measurement_property" in rows[0]

    assert "summary_report_docx:" in invocation.output
