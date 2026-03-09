"""Output builders for provisional end-to-end exports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from cosmin_assistant.review import provisional_review_state
from cosmin_assistant.tables.docx_stub import ProvisionalDocxExporter

if TYPE_CHECKING:
    from cosmin_assistant.cli.pipeline import ProvisionalAssessmentRun


def export_run_outputs(*, run: ProvisionalAssessmentRun, out_dir: str | Path) -> dict[str, str]:
    """Export provisional pipeline artifacts to JSON/MD/CSV/DOCX files."""

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    evidence_path = out_path / "evidence.json"
    rob_path = out_path / "rob_assessment.json"
    measurement_path = out_path / "measurement_property_results.json"
    synthesis_path = out_path / "synthesis.json"
    grade_path = out_path / "grade.json"
    summary_md_path = out_path / "summary_report.md"
    csv_path = out_path / "per_study_results.csv"
    docx_path = out_path / "summary_report.docx"
    review_overrides_path = out_path / "review_overrides.json"
    adjudication_notes_path = out_path / "adjudication_notes.json"
    review_state_path = out_path / "review_state.json"

    evidence_payload = {
        "profile": run.profile_type.value,
        "article_path": run.article_path,
        "parsed_document": run.parsed_document.model_dump(mode="json"),
        "context_extraction": run.context_extraction.model_dump(mode="json"),
        "statistics_extraction": run.statistics_extraction.model_dump(mode="json"),
    }
    _write_json(evidence_path, evidence_payload)
    _write_json(rob_path, [bundle.model_dump(mode="json") for bundle in run.rob_assessments])
    _write_json(
        measurement_path,
        [result.model_dump(mode="json") for result in run.measurement_property_results],
    )
    _write_json(
        synthesis_path,
        [result.model_dump(mode="json") for result in run.synthesis_results],
    )
    _write_json(grade_path, [result.model_dump(mode="json") for result in run.grade_results])
    _write_json(review_overrides_path, [])
    _write_json(adjudication_notes_path, [])
    _write_json(
        review_state_path,
        provisional_review_state(source_output_dir=str(out_path)).model_dump(mode="json"),
    )

    summary_markdown = _build_summary_markdown(run)
    summary_md_path.write_text(summary_markdown, encoding="utf-8")

    per_study_df = _build_per_study_dataframe(run)
    per_study_df.to_csv(csv_path, index=False)

    docx_exporter = ProvisionalDocxExporter()
    docx_exporter.export_summary(output_path=docx_path, report_markdown=summary_markdown)

    return {
        "evidence_json": str(evidence_path),
        "rob_assessment_json": str(rob_path),
        "measurement_property_results_json": str(measurement_path),
        "synthesis_json": str(synthesis_path),
        "grade_json": str(grade_path),
        "summary_report_md": str(summary_md_path),
        "per_study_csv": str(csv_path),
        "summary_report_docx": str(docx_path),
        "review_overrides_json": str(review_overrides_path),
        "adjudication_notes_json": str(adjudication_notes_path),
        "review_state_json": str(review_state_path),
    }


def _build_summary_markdown(run: ProvisionalAssessmentRun) -> str:
    lines = [
        "# COSMIN Assistant Provisional Summary",
        "",
        f"- Article: `{run.article_path}`",
        f"- Profile: `{run.profile_type.value}`",
        f"- Evidence spans: `{len(run.parsed_document.sentences)}` sentence-level spans",
        "",
        "## RoB Boxes",
    ]
    for bundle in run.rob_assessments:
        lines.append(
            f"- `{bundle.box_assessment.cosmin_box}`: "
            f"`{bundle.box_assessment.box_rating.value}` "
            f"(rule `{bundle.aggregation_rule}`)"
        )

    lines.append("")
    lines.append("## Measurement Property Ratings")
    for result in run.measurement_property_results:
        lines.append(
            f"- `{result.measurement_property}`: `{result.computed_rating.value}` "
            f"(rule `{result.rule_name}`)"
        )

    lines.append("")
    lines.append("## Synthesis")
    for synthesis in run.synthesis_results:
        lines.append(
            f"- `{synthesis.measurement_property}`: `{synthesis.summary_rating.value}` "
            f"(total_n={synthesis.total_sample_size})"
        )

    lines.append("")
    lines.append("## Modified GRADE")
    for grade in run.grade_results:
        lines.append(
            f"- `{grade.measurement_property}`: `{grade.starting_certainty.value}` -> "
            f"`{grade.final_certainty.value}` (downgrade_steps={grade.total_downgrade_steps})"
        )

    lines.append("")
    lines.append("_This is a provisional report for audit and debugging._")
    return "\n".join(lines) + "\n"


def _build_per_study_dataframe(run: ProvisionalAssessmentRun) -> pd.DataFrame:
    box_by_property = {
        bundle.box_assessment.measurement_property: bundle.box_assessment.box_rating.value
        for bundle in run.rob_assessments
    }
    grade_by_property = {
        result.measurement_property: result.final_certainty.value for result in run.grade_results
    }

    rows = []
    for result in run.measurement_property_results:
        rows.append(
            {
                "study_id": result.study_id,
                "instrument_id": result.instrument_id,
                "measurement_property": result.measurement_property,
                "box_rating": box_by_property.get(result.measurement_property, ""),
                "study_level_rating": result.computed_rating.value,
                "uncertainty_status": result.uncertainty_status.value,
                "reviewer_decision_status": result.reviewer_decision_status.value,
                "final_grade_certainty": grade_by_property.get(result.measurement_property, ""),
                "evidence_span_ids": ",".join(result.evidence_span_ids),
            }
        )
    return pd.DataFrame(rows)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
