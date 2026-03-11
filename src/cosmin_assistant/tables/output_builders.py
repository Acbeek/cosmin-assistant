"""Output builders for provisional end-to-end exports."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from cosmin_assistant import __version__
from cosmin_assistant.extract.context_models import InstrumentContextRole, StudyIntent
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
    from cosmin_assistant.measurement_rating.models import MeasurementPropertyRatingResult

_SUMMARY_INCLUDED_STATUSES: tuple[PropertyActivationStatus, ...] = (
    PropertyActivationStatus.DIRECT_CURRENT_STUDY_EVIDENCE,
    PropertyActivationStatus.MEASUREMENT_ERROR_SUPPORT_ONLY,
    PropertyActivationStatus.INTERPRETABILITY_ONLY,
    PropertyActivationStatus.REVIEWER_REQUIRED,
)
_ARTIFACT_BASENAMES: dict[str, str] = {
    "evidence_json": "evidence.json",
    "rob_assessment_json": "rob_assessment.json",
    "measurement_property_results_json": "measurement_property_results.json",
    "synthesis_json": "synthesis.json",
    "grade_json": "grade.json",
    "summary_report_md": "summary_report.md",
    "per_study_csv": "per_study_results.csv",
    "summary_report_docx": "summary_report.docx",
    "review_overrides_json": "review_overrides.json",
    "adjudication_notes_json": "adjudication_notes.json",
    "review_state_json": "review_state.json",
    "run_manifest_json": "run_manifest.json",
}


def export_run_outputs(*, run: ProvisionalAssessmentRun, out_dir: str | Path) -> dict[str, str]:
    """Export provisional pipeline artifacts to JSON/MD/CSV/DOCX files."""

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    artifact_prefix = _artifact_prefix_from_article_path(run.article_path)
    legacy_paths, prefixed_paths = _artifact_path_registry(
        out_path=out_path,
        artifact_prefix=artifact_prefix,
    )
    manifest_path = legacy_paths["run_manifest_json"]
    measurement_results_for_export = _measurement_results_for_export(run)

    _guard_against_stale_outputs(manifest_path=manifest_path, run=run)
    _guard_existing_artifact_coherence(
        run=run,
        evidence_path=legacy_paths["evidence_json"],
        measurement_path=legacy_paths["measurement_property_results_json"],
        synthesis_path=legacy_paths["synthesis_json"],
    )
    _guard_provenance_integrity(run)
    _guard_export_payload_coherence(
        run=run,
        measurement_results_for_export=measurement_results_for_export,
    )

    manifest_payload = {
        "python_version": python_version_string(),
        "package_version": __version__,
        "git_commit_if_available": git_commit_if_available(repo_root_from_file(run.article_path)),
        "profile": run.profile_type.value,
        "source_article_path": run.article_path,
        "source_article_hash": run.source_article_hash,
        "generated_at_utc": run.generated_at_utc,
        "artifact_prefix": artifact_prefix,
        "artifact_filenames_prefixed": {key: path.name for key, path in prefixed_paths.items()},
        "artifact_filenames_legacy": {key: path.name for key, path in legacy_paths.items()},
    }
    _write_json_with_legacy_alias(
        prefixed_path=prefixed_paths["run_manifest_json"],
        legacy_path=legacy_paths["run_manifest_json"],
        payload=manifest_payload,
    )

    evidence_payload = {
        "profile": run.profile_type.value,
        "article_path": run.article_path,
        "parsed_document": run.parsed_document.model_dump(mode="json"),
        "context_extraction": run.context_extraction.model_dump(mode="json"),
        "statistics_extraction": run.statistics_extraction.model_dump(mode="json"),
    }
    _write_json_with_legacy_alias(
        prefixed_path=prefixed_paths["evidence_json"],
        legacy_path=legacy_paths["evidence_json"],
        payload=evidence_payload,
    )
    _write_json_with_legacy_alias(
        prefixed_path=prefixed_paths["rob_assessment_json"],
        legacy_path=legacy_paths["rob_assessment_json"],
        payload=[bundle.model_dump(mode="json") for bundle in run.rob_assessments],
    )
    _write_json_with_legacy_alias(
        prefixed_path=prefixed_paths["measurement_property_results_json"],
        legacy_path=legacy_paths["measurement_property_results_json"],
        payload=[result.model_dump(mode="json") for result in measurement_results_for_export],
    )
    _write_json_with_legacy_alias(
        prefixed_path=prefixed_paths["synthesis_json"],
        legacy_path=legacy_paths["synthesis_json"],
        payload=[result.model_dump(mode="json") for result in run.synthesis_results],
    )
    _write_json_with_legacy_alias(
        prefixed_path=prefixed_paths["grade_json"],
        legacy_path=legacy_paths["grade_json"],
        payload=[result.model_dump(mode="json") for result in run.grade_results],
    )
    _write_json_with_legacy_alias(
        prefixed_path=prefixed_paths["review_overrides_json"],
        legacy_path=legacy_paths["review_overrides_json"],
        payload=[],
    )
    _write_json_with_legacy_alias(
        prefixed_path=prefixed_paths["adjudication_notes_json"],
        legacy_path=legacy_paths["adjudication_notes_json"],
        payload=[],
    )
    _write_json_with_legacy_alias(
        prefixed_path=prefixed_paths["review_state_json"],
        legacy_path=legacy_paths["review_state_json"],
        payload=provisional_review_state(source_output_dir=str(out_path)).model_dump(mode="json"),
    )

    summary_markdown = _build_summary_markdown(
        run,
        measurement_results=measurement_results_for_export,
    )
    _write_text_with_legacy_alias(
        prefixed_path=prefixed_paths["summary_report_md"],
        legacy_path=legacy_paths["summary_report_md"],
        content=summary_markdown,
    )

    per_study_df = _build_per_study_dataframe_for_results(
        run,
        measurement_results=measurement_results_for_export,
    )
    prefixed_csv_path = prefixed_paths["per_study_csv"]
    per_study_df.to_csv(prefixed_csv_path, index=False)
    _copy_with_legacy_alias(
        prefixed_path=prefixed_csv_path,
        legacy_path=legacy_paths["per_study_csv"],
    )

    docx_exporter = ProvisionalDocxExporter()
    prefixed_docx_path = prefixed_paths["summary_report_docx"]
    docx_exporter.export_summary(output_path=prefixed_docx_path, report_markdown=summary_markdown)
    _copy_with_legacy_alias(
        prefixed_path=prefixed_docx_path,
        legacy_path=legacy_paths["summary_report_docx"],
    )

    outputs = {key: str(path) for key, path in legacy_paths.items()}
    outputs.update({f"{key}_prefixed": str(path) for key, path in prefixed_paths.items()})
    return outputs


def _build_summary_markdown(
    run: ProvisionalAssessmentRun,
    *,
    measurement_results: tuple[MeasurementPropertyRatingResult, ...],
) -> str:
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
        for result in measurement_results
        if result.activation_status in _SUMMARY_INCLUDED_STATUSES
    ]
    suppressed_measurement = len(measurement_results) - len(summary_results)
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
    return _build_per_study_dataframe_for_results(
        run,
        measurement_results=run.measurement_property_results,
    )


def _build_per_study_dataframe_for_results(
    run: ProvisionalAssessmentRun,
    *,
    measurement_results: tuple[MeasurementPropertyRatingResult, ...],
) -> pd.DataFrame:
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
    for result in measurement_results:
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


def _measurement_results_for_export(
    run: ProvisionalAssessmentRun,
) -> tuple[MeasurementPropertyRatingResult, ...]:
    harmonized = _harmonize_measurement_results_with_synthesis_targets(
        run,
        measurement_results=run.measurement_property_results,
    )
    if not _is_multi_outcome_interpretability_run(run):
        return harmonized

    name_by_id = {
        context.instrument_id: (
            context.instrument_name.candidates[0].normalized_value
            if context.instrument_name.candidates
            else context.instrument_id
        )
        for context in run.context_extraction.instrument_contexts
    }
    synthesis_keys = {
        (result.instrument_name, result.measurement_property, result.activation_status)
        for result in run.synthesis_results
    }

    filtered = tuple(
        result
        for result in harmonized
        if (
            str(name_by_id.get(result.instrument_id, result.instrument_id)),
            result.measurement_property,
            result.activation_status,
        )
        in synthesis_keys
    )
    return filtered


def _harmonize_measurement_results_with_synthesis_targets(
    run: ProvisionalAssessmentRun,
    *,
    measurement_results: tuple[MeasurementPropertyRatingResult, ...],
) -> tuple[MeasurementPropertyRatingResult, ...]:
    """Keep active measurement rows aligned to the surviving synthesis target set."""

    name_by_id = {
        context.instrument_id: (
            str(context.instrument_name.candidates[0].normalized_value)
            if context.instrument_name.candidates
            else "unknown"
        )
        for context in run.context_extraction.instrument_contexts
    }
    synthesis_keys = {
        (
            result.instrument_name,
            result.measurement_property,
            result.activation_status,
        )
        for result in run.synthesis_results
    }

    harmonized: list[MeasurementPropertyRatingResult] = []
    for result in measurement_results:
        if result.activation_status not in _SUMMARY_INCLUDED_STATUSES:
            harmonized.append(result)
            continue

        key = (
            name_by_id.get(result.instrument_id, "unknown"),
            result.measurement_property,
            result.activation_status,
        )
        if key in synthesis_keys:
            harmonized.append(result)

    return tuple(harmonized)


def _is_multi_outcome_interpretability_run(run: ProvisionalAssessmentRun) -> bool:
    if not run.context_extraction.study_contexts:
        return False
    if run.context_extraction.study_contexts[0].study_intent is not StudyIntent.MIXED:
        return False

    co_studied_contexts = [
        context
        for context in run.context_extraction.instrument_contexts
        if context.instrument_role
        in (
            InstrumentContextRole.CO_PRIMARY_OUTCOME_INSTRUMENT,
            InstrumentContextRole.SECONDARY_OUTCOME_INSTRUMENT,
            InstrumentContextRole.TARGET_UNDER_APPRAISAL,
        )
    ]
    if len(co_studied_contexts) < 2:
        return False

    has_interpretability_only = any(
        result.measurement_property == "interpretability"
        and result.activation_status is PropertyActivationStatus.INTERPRETABILITY_ONLY
        for result in run.measurement_property_results
    )
    return has_interpretability_only


def _artifact_prefix_from_article_path(article_path: str) -> str:
    raw_stem = Path(article_path).stem
    with_underscores = re.sub(r"\s+", "_", raw_stem.strip())
    sanitized = re.sub(r"[^A-Za-z0-9_-]", "", with_underscores)
    compacted = re.sub(r"_+", "_", sanitized).strip("._-")
    return compacted or "article"


def _artifact_path_registry(
    *,
    out_path: Path,
    artifact_prefix: str,
) -> tuple[dict[str, Path], dict[str, Path]]:
    legacy_paths = {key: out_path / basename for key, basename in _ARTIFACT_BASENAMES.items()}
    prefixed_paths = {
        key: out_path / f"{artifact_prefix}__{basename}"
        for key, basename in _ARTIFACT_BASENAMES.items()
    }
    return legacy_paths, prefixed_paths


def _write_json_with_legacy_alias(
    *,
    prefixed_path: Path,
    legacy_path: Path,
    payload: object,
) -> None:
    _write_json(prefixed_path, payload)
    if prefixed_path != legacy_path:
        _copy_with_legacy_alias(prefixed_path=prefixed_path, legacy_path=legacy_path)


def _write_text_with_legacy_alias(
    *,
    prefixed_path: Path,
    legacy_path: Path,
    content: str,
) -> None:
    prefixed_path.write_text(content, encoding="utf-8")
    if prefixed_path != legacy_path:
        _copy_with_legacy_alias(prefixed_path=prefixed_path, legacy_path=legacy_path)


def _copy_with_legacy_alias(*, prefixed_path: Path, legacy_path: Path) -> None:
    if prefixed_path == legacy_path:
        return
    shutil.copyfile(prefixed_path, legacy_path)


def _guard_against_stale_outputs(*, manifest_path: Path, run: ProvisionalAssessmentRun) -> None:
    if not manifest_path.exists():
        return

    try:
        prior = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        msg = (
            "Output directory contains an unreadable run_manifest.json. "
            "Remove stale artifacts or choose a clean output directory."
        )
        raise ValueError(msg) from None

    prior_path = prior.get("source_article_path")
    prior_hash = prior.get("source_article_hash")
    if prior_path and prior_path != run.article_path:
        msg = (
            "Output directory already contains artifacts for a different source article path. "
            "Use a new output directory or remove old outputs."
        )
        raise ValueError(msg)
    if prior_hash and prior_hash != run.source_article_hash:
        msg = (
            "Output directory contains stale artifacts for the same source path but a different "
            "article hash. Use a new output directory or remove old outputs."
        )
        raise ValueError(msg)


def _guard_existing_artifact_coherence(
    *,
    run: ProvisionalAssessmentRun,
    evidence_path: Path,
    measurement_path: Path,
    synthesis_path: Path,
) -> None:
    existing_paths = [
        path for path in (evidence_path, measurement_path, synthesis_path) if path.exists()
    ]
    if not existing_paths:
        return

    if not (evidence_path.exists() and measurement_path.exists() and synthesis_path.exists()):
        msg = (
            "Output directory contains partial prior artifacts. Remove stale outputs or use "
            "a clean directory before exporting."
        )
        raise ValueError(msg)

    try:
        evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        measurement_payload = json.loads(measurement_path.read_text(encoding="utf-8"))
        synthesis_payload = json.loads(synthesis_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        msg = (
            "Existing artifact coherence check failed because at least one core JSON artifact "
            f"is unreadable: {exc}."
        )
        raise ValueError(msg) from exc

    if not (
        isinstance(evidence_payload, dict)
        and isinstance(measurement_payload, list)
        and isinstance(synthesis_payload, list)
    ):
        msg = (
            "Existing artifact coherence check failed because core artifacts did not match "
            "expected payload shapes."
        )
        raise ValueError(msg)

    evidence_article_path = str(evidence_payload.get("article_path", ""))
    parsed_document = evidence_payload.get("parsed_document")
    parsed_article_path = ""
    if isinstance(parsed_document, dict):
        parsed_article_path = str(parsed_document.get("file_path", ""))

    if evidence_article_path and evidence_article_path != run.article_path:
        msg = (
            "Existing artifact coherence check failed because evidence.json was generated from "
            "a different source article."
        )
        raise ValueError(msg)
    if parsed_article_path and parsed_article_path != run.article_path:
        msg = (
            "Existing artifact coherence check failed because parsed_document.file_path in "
            "evidence.json does not match the current source article."
        )
        raise ValueError(msg)

    context_extraction = evidence_payload.get("context_extraction")
    if not isinstance(context_extraction, dict):
        msg = (
            "Existing artifact coherence check failed because evidence.json did not include "
            "context_extraction payload."
        )
        raise ValueError(msg)

    context_instrument_name_by_id = _context_instrument_name_by_id(
        context_extraction.get("instrument_contexts")
    )
    context_study_ids = _context_study_ids(context_extraction.get("study_contexts"))

    measurement_keys, measurement_study_ids = _measurement_payload_keys_and_study_ids(
        payload=measurement_payload,
        instrument_name_by_id=context_instrument_name_by_id,
    )
    synthesis_keys, synthesis_study_ids = _synthesis_payload_keys_and_study_ids(
        payload=synthesis_payload
    )

    if not synthesis_keys <= measurement_keys:
        missing = sorted(synthesis_keys - measurement_keys)
        preview = ", ".join(str(item) for item in missing[:5])
        msg = (
            "Existing artifact coherence check failed: synthesis.json rows were not backed by "
            f"measurement_property_results.json rows ({preview})."
        )
        raise ValueError(msg)

    if context_study_ids and (
        not measurement_study_ids <= context_study_ids
        or not synthesis_study_ids <= context_study_ids
    ):
        msg = (
            "Existing artifact coherence check failed because study_id values disagreed across "
            "evidence.json, measurement_property_results.json, and synthesis.json."
        )
        raise ValueError(msg)


def _guard_export_payload_coherence(
    *,
    run: ProvisionalAssessmentRun,
    measurement_results_for_export: tuple[MeasurementPropertyRatingResult, ...],
) -> None:
    if run.parsed_document.file_path != run.article_path:
        msg = (
            "Artifact coherence check failed: parsed document path does not match run "
            "source_article_path."
        )
        raise ValueError(msg)

    article_id = run.parsed_document.id
    if run.context_extraction.article_id != article_id:
        msg = (
            "Artifact coherence check failed: context extraction article_id does not match "
            "the parsed document."
        )
        raise ValueError(msg)
    if run.statistics_extraction.article_id != article_id:
        msg = (
            "Artifact coherence check failed: statistics extraction article_id does not match "
            "the parsed document."
        )
        raise ValueError(msg)

    context_study_ids = {study.study_id for study in run.context_extraction.study_contexts}
    measurement_study_ids = {result.study_id for result in measurement_results_for_export}
    synthesis_study_ids = {
        entry.study_id for synthesis in run.synthesis_results for entry in synthesis.study_entries
    }
    if not measurement_study_ids <= context_study_ids:
        msg = (
            "Artifact coherence check failed: measurement_property_results study_id values are "
            "not present in context extraction."
        )
        raise ValueError(msg)
    if not synthesis_study_ids <= context_study_ids:
        msg = (
            "Artifact coherence check failed: synthesis study_id values are not present in "
            "context extraction."
        )
        raise ValueError(msg)

    context_instrument_name_by_id = {
        context.instrument_id: (
            str(context.instrument_name.candidates[0].normalized_value)
            if context.instrument_name.candidates
            else "unknown"
        )
        for context in run.context_extraction.instrument_contexts
    }
    unknown_measurement_instrument_ids = {
        result.instrument_id
        for result in measurement_results_for_export
        if result.instrument_id not in context_instrument_name_by_id
    }
    if unknown_measurement_instrument_ids:
        preview = ", ".join(sorted(unknown_measurement_instrument_ids))
        msg = (
            "Artifact coherence check failed: measurement_property_results instrument_id values "
            f"were not found in context extraction ({preview})."
        )
        raise ValueError(msg)

    measurement_keys = {
        (
            context_instrument_name_by_id.get(result.instrument_id, "unknown"),
            result.measurement_property,
            result.activation_status.value,
        )
        for result in measurement_results_for_export
    }
    synthesis_keys = {
        (
            synthesis.instrument_name,
            synthesis.measurement_property,
            synthesis.activation_status.value,
        )
        for synthesis in run.synthesis_results
    }
    if not synthesis_keys <= measurement_keys:
        missing = sorted(synthesis_keys - measurement_keys)
        preview = ", ".join(str(item) for item in missing[:5])
        msg = (
            "Artifact coherence check failed: synthesis rows were not backed by exported "
            f"measurement_property_results rows ({preview})."
        )
        raise ValueError(msg)

    synthesis_ids = {synthesis.id for synthesis in run.synthesis_results}
    dangling_grade_synthesis_ids = {
        grade.synthesis_id for grade in run.grade_results if grade.synthesis_id not in synthesis_ids
    }
    if dangling_grade_synthesis_ids:
        preview = ", ".join(sorted(dangling_grade_synthesis_ids))
        msg = (
            "Artifact coherence check failed: grade rows referenced synthesis_id values that "
            f"were not present in synthesis results ({preview})."
        )
        raise ValueError(msg)


def _context_instrument_name_by_id(
    instrument_contexts_payload: object,
) -> dict[str, str]:
    if not isinstance(instrument_contexts_payload, list):
        return {}

    mapping: dict[str, str] = {}
    for context in instrument_contexts_payload:
        if not isinstance(context, dict):
            continue
        instrument_id = context.get("instrument_id")
        if not isinstance(instrument_id, str):
            continue

        resolved_name = "unknown"
        instrument_name_field = context.get("instrument_name")
        if isinstance(instrument_name_field, dict):
            candidates = instrument_name_field.get("candidates")
            if isinstance(candidates, list) and candidates:
                first = candidates[0]
                if isinstance(first, dict):
                    normalized = first.get("normalized_value")
                    if isinstance(normalized, str) and normalized.strip():
                        resolved_name = normalized

        mapping[instrument_id] = resolved_name

    return mapping


def _context_study_ids(study_contexts_payload: object) -> set[str]:
    if not isinstance(study_contexts_payload, list):
        return set()
    return {
        study_id
        for item in study_contexts_payload
        if isinstance(item, dict)
        for study_id in [item.get("study_id")]
        if isinstance(study_id, str)
    }


def _measurement_payload_keys_and_study_ids(
    *,
    payload: list[object],
    instrument_name_by_id: dict[str, str],
) -> tuple[set[tuple[str, str, str]], set[str]]:
    keys: set[tuple[str, str, str]] = set()
    study_ids: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        instrument_id = item.get("instrument_id")
        measurement_property = item.get("measurement_property")
        activation_status = item.get("activation_status")
        study_id = item.get("study_id")
        if (
            isinstance(instrument_id, str)
            and isinstance(measurement_property, str)
            and isinstance(activation_status, str)
        ):
            keys.add(
                (
                    instrument_name_by_id.get(instrument_id, "unknown"),
                    measurement_property,
                    activation_status,
                )
            )
        if isinstance(study_id, str):
            study_ids.add(study_id)
    return keys, study_ids


def _synthesis_payload_keys_and_study_ids(
    *,
    payload: list[object],
) -> tuple[set[tuple[str, str, str]], set[str]]:
    keys: set[tuple[str, str, str]] = set()
    study_ids: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        instrument_name = item.get("instrument_name")
        measurement_property = item.get("measurement_property")
        activation_status = item.get("activation_status")
        if (
            isinstance(instrument_name, str)
            and isinstance(measurement_property, str)
            and isinstance(activation_status, str)
        ):
            keys.add((instrument_name, measurement_property, activation_status))

        study_entries = item.get("study_entries")
        if not isinstance(study_entries, list):
            continue
        for entry in study_entries:
            if not isinstance(entry, dict):
                continue
            study_id = entry.get("study_id")
            if isinstance(study_id, str):
                study_ids.add(study_id)
    return keys, study_ids


def _guard_provenance_integrity(run: ProvisionalAssessmentRun) -> None:
    valid_span_ids = {
        span.id
        for span in (
            run.parsed_document.headings
            + run.parsed_document.paragraphs
            + run.parsed_document.sentences
        )
    }
    invalid_references: list[tuple[str, str]] = []

    def collect(location: str, evidence_span_ids: tuple[str, ...] | list[str]) -> None:
        for evidence_span_id in evidence_span_ids:
            if evidence_span_id and evidence_span_id not in valid_span_ids:
                invalid_references.append((location, evidence_span_id))

    for study_context in run.context_extraction.study_contexts:
        for field_name in (
            "study_design",
            "sample_sizes",
            "validation_sample_n",
            "pilot_sample_n",
            "retest_sample_n",
            "follow_up_schedule",
            "follow_up_interval",
            "construct_field",
            "target_population",
            "recruitment_setting",
            "language",
            "country",
            "measurement_properties_mentioned",
            "measurement_properties_background",
            "measurement_properties_interpretability",
            "measurement_properties_not_assessed",
        ):
            field = getattr(study_context, field_name)
            if field is None:
                continue
            for candidate in field.candidates:
                collect(f"study_context.{field_name}", candidate.evidence_span_ids)
        collect("study_context.study_intent", study_context.study_intent_evidence_span_ids)
        for observation in study_context.sample_size_observations:
            collect("study_context.sample_size_observations", observation.evidence_span_ids)
        for subsample in study_context.subsamples:
            collect("study_context.subsamples", subsample.evidence_span_ids)

    for instrument_context in run.context_extraction.instrument_contexts:
        for field_name in (
            "instrument_name",
            "instrument_version",
            "subscale",
            "construct_field",
            "target_population",
        ):
            field = getattr(instrument_context, field_name)
            for candidate in field.candidates:
                collect(f"instrument_context.{field_name}", candidate.evidence_span_ids)
        collect(
            "instrument_context.instrument_type",
            instrument_context.instrument_type_evidence_span_ids,
        )
        collect("instrument_context.instrument_role", instrument_context.role_evidence_span_ids)

    for candidate in run.statistics_extraction.candidates:
        collect("statistics", candidate.evidence_span_ids)
    for activation_decision in run.property_activation_decisions:
        collect("property_activation", activation_decision.evidence_span_ids)

    for bundle in run.rob_assessments:
        collect("rob.box", bundle.box_assessment.evidence_span_ids)
        for item in bundle.item_assessments:
            collect("rob.item", item.evidence_span_ids)

    for result in run.measurement_property_results:
        collect("measurement_result", result.evidence_span_ids)
        for raw in result.raw_results:
            collect("measurement_result.raw", raw.evidence_span_ids)
        for prerequisite in result.prerequisite_decisions:
            collect("measurement_result.prerequisite", prerequisite.evidence_span_ids)
        for threshold in result.threshold_comparisons:
            collect("measurement_result.threshold", threshold.evidence_span_ids)

    for synthesis in run.synthesis_results:
        collect("synthesis", synthesis.evidence_span_ids)
        for entry in synthesis.study_entries:
            collect("synthesis.study_entry", entry.evidence_span_ids)
        for placeholder in synthesis.subgroup_explanation_placeholders:
            collect("synthesis.subgroup_placeholder", placeholder.evidence_span_ids)

    for grade in run.grade_results:
        collect("grade", grade.evidence_span_ids)
        for grade_decision in grade.domain_decisions:
            collect("grade.domain_decision", grade_decision.evidence_span_ids)
        for record in grade.downgrade_records:
            collect("grade.downgrade_record", record.evidence_span_ids)

    if invalid_references:
        sample = ", ".join(f"{location}:{span_id}" for location, span_id in invalid_references[:8])
        msg = (
            "Provenance integrity check failed: evidence_span_ids must resolve to spans "
            f"from the current parsed article run. Invalid references: {sample}"
        )
        raise ValueError(msg)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
