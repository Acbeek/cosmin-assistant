"""Output builders for provisional end-to-end exports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from cosmin_assistant import __version__
from cosmin_assistant.models import PropertyActivationStatus
from cosmin_assistant.review import provisional_review_state
from cosmin_assistant.tables.docx_stub import ProvisionalDocxExporter
from cosmin_assistant.utils import (
    git_commit_if_available,
    python_version_string,
    repo_root_from_file,
)

if TYPE_CHECKING:
    from cosmin_assistant.cli.pipeline import ProvisionalAssessmentRun

_SUMMARY_INCLUDED_STATUSES: tuple[PropertyActivationStatus, ...] = (
    PropertyActivationStatus.DIRECT_CURRENT_STUDY_EVIDENCE,
    PropertyActivationStatus.MEASUREMENT_ERROR_SUPPORT_ONLY,
    PropertyActivationStatus.INTERPRETABILITY_ONLY,
    PropertyActivationStatus.REVIEWER_REQUIRED,
)


def export_run_outputs(*, run: ProvisionalAssessmentRun, out_dir: str | Path) -> dict[str, str]:
    """Export provisional pipeline artifacts to JSON/MD/CSV/DOCX files."""

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    manifest_path = out_path / "run_manifest.json"
    _guard_against_stale_outputs(manifest_path=manifest_path, run=run)

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

    manifest_payload = {
        "python_version": python_version_string(),
        "package_version": __version__,
        "git_commit_if_available": git_commit_if_available(repo_root_from_file(run.article_path)),
        "profile": run.profile_type.value,
        "source_article_path": run.article_path,
        "source_article_hash": run.source_article_hash,
        "generated_at_utc": run.generated_at_utc,
    }
    _write_json(manifest_path, manifest_payload)

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
        "run_manifest_json": str(manifest_path),
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
    summary_results = [
        result
        for result in run.measurement_property_results
        if result.activation_status in _SUMMARY_INCLUDED_STATUSES
    ]
    suppressed_measurement = len(run.measurement_property_results) - len(summary_results)
    for result in summary_results:
        lines.append(
            f"- `{result.instrument_id}` / `{result.measurement_property}`: "
            f"`{result.computed_rating.value}` "
            f"(rule `{result.rule_name}`; activation_status=`{result.activation_status.value}`)"
        )
    if suppressed_measurement > 0:
        lines.append(
            f"- Suppressed `{suppressed_measurement}` non-assessed/indirect/not-applicable "
            "measurement rows for readability."
        )

    lines.append("")
    lines.append("## Synthesis")
    summary_synthesis = [
        synthesis
        for synthesis in run.synthesis_results
        if synthesis.activation_status in _SUMMARY_INCLUDED_STATUSES
    ]
    suppressed_synthesis = len(run.synthesis_results) - len(summary_synthesis)
    for synthesis in summary_synthesis:
        lines.append(
            f"- `{synthesis.instrument_name}` / `{synthesis.measurement_property}`: "
            f"`{synthesis.summary_rating.value}` "
            f"(total_n={synthesis.total_sample_size}; "
            f"activation_status=`{synthesis.activation_status.value}`)"
        )
    if suppressed_synthesis > 0:
        lines.append(
            f"- Suppressed `{suppressed_synthesis}` non-assessed/indirect/not-applicable "
            "synthesis rows for readability."
        )

    lines.append("")
    lines.append("## Modified GRADE")
    for grade in run.grade_results:
        if not grade.grade_executed:
            lines.append(
                f"- `{grade.measurement_property}`: `not_graded` "
                f"(activation_status=`{grade.activation_status.value}`; "
                f"reason={grade.explanation})"
            )
            continue
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
        result.measurement_property: (
            result.final_certainty.value if result.grade_executed else "not_graded"
        )
        for result in run.grade_results
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


def _guard_against_stale_outputs(*, manifest_path: Path, run: ProvisionalAssessmentRun) -> None:
    if not manifest_path.exists():
        return

    try:
        prior = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return

    prior_path = prior.get("source_article_path")
    prior_hash = prior.get("source_article_hash")
    if prior_path == run.article_path and prior_hash and prior_hash != run.source_article_hash:
        msg = (
            "Output directory contains stale artifacts for the same source path but a different "
            "article hash. Use a new output directory or remove old outputs."
        )
        raise ValueError(msg)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
