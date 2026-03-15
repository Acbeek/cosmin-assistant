"""Reviewer override and adjudication flow for provisional JSON outputs."""

from __future__ import annotations

import hashlib
import json
import shutil
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from cosmin_assistant.models import (
    CosminBoxRating,
    CosminItemRating,
    MeasurementPropertyRating,
    ReviewerDecisionStatus,
    ReviewerOverride,
    UncertaintyStatus,
)
from cosmin_assistant.review.models import (
    AdjudicationNoteRequest,
    OverrideTargetType,
    PendingReviewItem,
    ReviewerAdjudicationNote,
    ReviewOverrideRequest,
    ReviewRequestBundle,
    ReviewState,
    ReviewStatus,
)
from cosmin_assistant.tables.docx_stub import ProvisionalDocxExporter

EVIDENCE_FILE = "evidence.json"
ROB_FILE = "rob_assessment.json"
MEASUREMENT_FILE = "measurement_property_results.json"
SYNTHESIS_FILE = "synthesis.json"
GRADE_FILE = "grade.json"
SUMMARY_FILE = "summary_report.md"
CSV_FILE = "per_study_results.csv"
DOCX_FILE = "summary_report.docx"
OVERRIDES_FILE = "review_overrides.json"
ADJUDICATIONS_FILE = "adjudication_notes.json"
REVIEW_STATE_FILE = "review_state.json"
RUN_MANIFEST_FILE = "run_manifest.json"


@dataclass(frozen=True)
class _FieldSpec:
    kind: str
    allowed_values: frozenset[str] | None = None


_ALLOWED_OVERRIDE_FIELDS: dict[OverrideTargetType, dict[str, _FieldSpec]] = {
    OverrideTargetType.ROB_ITEM_ASSESSMENT: {
        "item_rating": _FieldSpec(
            kind="enum",
            allowed_values=frozenset(item.value for item in CosminItemRating),
        ),
        "uncertainty_status": _FieldSpec(
            kind="enum",
            allowed_values=frozenset(item.value for item in UncertaintyStatus),
        ),
        "reviewer_decision_status": _FieldSpec(
            kind="enum",
            allowed_values=frozenset(item.value for item in ReviewerDecisionStatus),
        ),
    },
    OverrideTargetType.ROB_BOX_ASSESSMENT: {
        "box_rating": _FieldSpec(
            kind="enum",
            allowed_values=frozenset(item.value for item in CosminBoxRating),
        ),
        "uncertainty_status": _FieldSpec(
            kind="enum",
            allowed_values=frozenset(item.value for item in UncertaintyStatus),
        ),
        "reviewer_decision_status": _FieldSpec(
            kind="enum",
            allowed_values=frozenset(item.value for item in ReviewerDecisionStatus),
        ),
    },
    OverrideTargetType.MEASUREMENT_PROPERTY_RESULT: {
        "computed_rating": _FieldSpec(
            kind="enum",
            allowed_values=frozenset(item.value for item in MeasurementPropertyRating),
        ),
        "explanation": _FieldSpec(kind="string"),
        "uncertainty_status": _FieldSpec(
            kind="enum",
            allowed_values=frozenset(item.value for item in UncertaintyStatus),
        ),
        "reviewer_decision_status": _FieldSpec(
            kind="enum",
            allowed_values=frozenset(item.value for item in ReviewerDecisionStatus),
        ),
    },
    OverrideTargetType.SYNTHESIS_RESULT: {
        "summary_rating": _FieldSpec(
            kind="enum",
            allowed_values=frozenset(item.value for item in MeasurementPropertyRating),
        ),
        "summary_explanation": _FieldSpec(kind="string"),
        "inconsistent_findings": _FieldSpec(kind="boolean"),
        "requires_subgroup_explanation": _FieldSpec(kind="boolean"),
    },
    OverrideTargetType.GRADE_RESULT: {
        "final_certainty": _FieldSpec(
            kind="enum",
            allowed_values=frozenset({"high", "moderate", "low", "very_low"}),
        ),
        "explanation": _FieldSpec(kind="string"),
    },
}


def load_review_request_file(path: str | Path) -> ReviewRequestBundle:
    """Load review request YAML/JSON file into a typed request bundle."""

    request_path = Path(path)
    raw_text = request_path.read_text(encoding="utf-8")

    if request_path.suffix.lower() in {".yaml", ".yml"}:
        payload = yaml.safe_load(raw_text) or {}
    else:
        payload = json.loads(raw_text)

    return ReviewRequestBundle.model_validate(payload)


def apply_review_request_file(
    *,
    provisional_dir: str | Path,
    review_file: str | Path,
    out_dir: str | Path | None = None,
    finalize: bool | None = None,
) -> dict[str, str]:
    """Apply overrides from file to provisional outputs and export reviewed artifacts."""

    request = load_review_request_file(review_file)
    if finalize is not None:
        request = ReviewRequestBundle(
            overrides=request.overrides,
            adjudication_notes=request.adjudication_notes,
            finalize=finalize,
        )
    return apply_review_request_bundle(
        provisional_dir=provisional_dir,
        request=request,
        out_dir=out_dir,
    )


def apply_review_request_bundle(
    *,
    provisional_dir: str | Path,
    request: ReviewRequestBundle,
    out_dir: str | Path | None = None,
) -> dict[str, str]:
    """Apply review overrides and adjudications to provisional JSON outputs."""

    source_dir = Path(provisional_dir).expanduser().resolve()
    source_manifest_path, source_prefixed_manifest_paths = _manifest_copy_sources(source_dir)
    evidence_payload = _load_required_json(source_dir / EVIDENCE_FILE)
    rob_payload = _load_required_json(source_dir / ROB_FILE)
    measurement_payload = _load_required_json(source_dir / MEASUREMENT_FILE)
    synthesis_payload = _load_required_json(source_dir / SYNTHESIS_FILE)
    grade_payload = _load_required_json(source_dir / GRADE_FILE)

    reviewed_rob = deepcopy(rob_payload)
    reviewed_measurement = deepcopy(measurement_payload)
    reviewed_synthesis = deepcopy(synthesis_payload)
    reviewed_grade = deepcopy(grade_payload)

    target_index = _build_target_index(
        rob_payload=reviewed_rob,
        measurement_payload=reviewed_measurement,
        synthesis_payload=reviewed_synthesis,
        grade_payload=reviewed_grade,
    )

    existing_overrides = _load_existing_overrides(source_dir / OVERRIDES_FILE)
    existing_adjudications = _load_existing_adjudications(source_dir / ADJUDICATIONS_FILE)

    new_overrides = _apply_overrides(
        overrides=request.overrides,
        target_index=target_index,
        existing_override_count=len(existing_overrides),
    )
    new_adjudications = _build_adjudications(
        requests=request.adjudication_notes,
        existing_note_count=len(existing_adjudications),
    )

    all_overrides = tuple(existing_overrides) + tuple(new_overrides)
    all_adjudications = tuple(existing_adjudications) + tuple(new_adjudications)

    pending_review_items = _collect_pending_review_items(
        evidence_payload=evidence_payload,
        rob_payload=reviewed_rob,
        measurement_payload=reviewed_measurement,
        synthesis_payload=reviewed_synthesis,
    )

    review_status = ReviewStatus.FINALIZED if request.finalize else ReviewStatus.PROVISIONAL
    review_state = ReviewState(
        id=_stable_id(
            "reviewstate",
            str(source_dir),
            review_status.value,
            len(all_overrides),
            len(all_adjudications),
        ),
        review_status=review_status,
        finalized=review_status is ReviewStatus.FINALIZED,
        source_output_dir=str(source_dir),
        generated_at_utc=datetime.now(UTC),
        overrides_applied_in_run=len(new_overrides),
        overrides_total=len(all_overrides),
        adjudication_notes_added_in_run=len(new_adjudications),
        adjudication_notes_total=len(all_adjudications),
        pending_review_items=pending_review_items,
    )

    destination_dir = _resolve_output_dir(
        source_dir=source_dir,
        out_dir=out_dir,
        review_status=review_status,
    )
    destination_dir.mkdir(parents=True, exist_ok=True)

    evidence_path = destination_dir / EVIDENCE_FILE
    rob_path = destination_dir / ROB_FILE
    measurement_path = destination_dir / MEASUREMENT_FILE
    synthesis_path = destination_dir / SYNTHESIS_FILE
    grade_path = destination_dir / GRADE_FILE
    summary_path = destination_dir / SUMMARY_FILE
    csv_path = destination_dir / CSV_FILE
    docx_path = destination_dir / DOCX_FILE
    overrides_path = destination_dir / OVERRIDES_FILE
    adjudications_path = destination_dir / ADJUDICATIONS_FILE
    review_state_path = destination_dir / REVIEW_STATE_FILE
    run_manifest_path = destination_dir / RUN_MANIFEST_FILE

    _write_json(evidence_path, evidence_payload)
    _write_json(rob_path, reviewed_rob)
    _write_json(measurement_path, reviewed_measurement)
    _write_json(synthesis_path, reviewed_synthesis)
    _write_json(grade_path, reviewed_grade)
    _write_json(overrides_path, [item.model_dump(mode="json") for item in all_overrides])
    _write_json(adjudications_path, [item.model_dump(mode="json") for item in all_adjudications])
    _write_json(review_state_path, review_state.model_dump(mode="json"))
    shutil.copyfile(source_manifest_path, run_manifest_path)

    copied_prefixed_manifests: list[Path] = []
    for source_prefixed_manifest in source_prefixed_manifest_paths:
        destination_prefixed_manifest = destination_dir / source_prefixed_manifest.name
        shutil.copyfile(source_prefixed_manifest, destination_prefixed_manifest)
        copied_prefixed_manifests.append(destination_prefixed_manifest)

    summary_markdown = _build_review_summary_markdown(
        review_state=review_state,
        measurement_payload=reviewed_measurement,
        synthesis_payload=reviewed_synthesis,
        grade_payload=reviewed_grade,
    )
    summary_path.write_text(summary_markdown, encoding="utf-8")

    per_study_df = _build_per_study_dataframe(
        rob_payload=reviewed_rob,
        measurement_payload=reviewed_measurement,
        grade_payload=reviewed_grade,
    )
    per_study_df.to_csv(csv_path, index=False)

    docx_exporter = ProvisionalDocxExporter()
    docx_exporter.export_summary(output_path=docx_path, report_markdown=summary_markdown)

    outputs = {
        "evidence_json": str(evidence_path),
        "rob_assessment_json": str(rob_path),
        "measurement_property_results_json": str(measurement_path),
        "synthesis_json": str(synthesis_path),
        "grade_json": str(grade_path),
        "summary_report_md": str(summary_path),
        "per_study_csv": str(csv_path),
        "summary_report_docx": str(docx_path),
        "review_overrides_json": str(overrides_path),
        "adjudication_notes_json": str(adjudications_path),
        "review_state_json": str(review_state_path),
        "run_manifest_json": str(run_manifest_path),
    }
    if copied_prefixed_manifests:
        outputs["run_manifest_json_prefixed"] = str(copied_prefixed_manifests[0])
    return outputs


def _manifest_copy_sources(source_dir: Path) -> tuple[Path, tuple[Path, ...]]:
    manifest_path = source_dir / RUN_MANIFEST_FILE
    manifest_payload = _load_required_json(manifest_path)
    if not isinstance(manifest_payload, dict):
        msg = f"{RUN_MANIFEST_FILE} must contain a JSON object payload."
        raise ValueError(msg)

    prefixed_manifest_names: list[str] = []
    prefixed_section = manifest_payload.get("artifact_filenames_prefixed")
    if isinstance(prefixed_section, dict):
        prefixed_name = prefixed_section.get("run_manifest_json")
        if (
            isinstance(prefixed_name, str)
            and prefixed_name.strip()
            and prefixed_name != RUN_MANIFEST_FILE
        ):
            prefixed_manifest_names.append(prefixed_name)

    for candidate in sorted(source_dir.glob(f"*__{RUN_MANIFEST_FILE}")):
        if candidate.name not in prefixed_manifest_names:
            prefixed_manifest_names.append(candidate.name)

    prefixed_paths: list[Path] = []
    for prefixed_name in prefixed_manifest_names:
        prefixed_path = source_dir / prefixed_name
        if not prefixed_path.exists():
            msg = (
                f"{RUN_MANIFEST_FILE} declares a prefixed manifest that is missing: "
                f"{prefixed_path}"
            )
            raise ValueError(msg)
        prefixed_paths.append(prefixed_path)

    return manifest_path, tuple(prefixed_paths)


def _load_required_json(path: Path) -> Any:
    if not path.exists():
        msg = f"required provisional output file is missing: {path}"
        raise ValueError(msg)
    return json.loads(path.read_text(encoding="utf-8"))


def _load_existing_overrides(path: Path) -> tuple[ReviewerOverride, ...]:
    if not path.exists():
        return ()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return tuple(ReviewerOverride.model_validate(item) for item in payload)


def _load_existing_adjudications(path: Path) -> tuple[ReviewerAdjudicationNote, ...]:
    if not path.exists():
        return ()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return tuple(ReviewerAdjudicationNote.model_validate(item) for item in payload)


def _build_target_index(
    *,
    rob_payload: list[dict[str, Any]],
    measurement_payload: list[dict[str, Any]],
    synthesis_payload: list[dict[str, Any]],
    grade_payload: list[dict[str, Any]],
) -> dict[tuple[OverrideTargetType, str], dict[str, Any]]:
    index: dict[tuple[OverrideTargetType, str], dict[str, Any]] = {}

    for bundle in rob_payload:
        box_assessment = bundle.get("box_assessment")
        if isinstance(box_assessment, dict) and "id" in box_assessment:
            key = (OverrideTargetType.ROB_BOX_ASSESSMENT, str(box_assessment["id"]))
            index[key] = box_assessment

        for item in bundle.get("item_assessments", []):
            if isinstance(item, dict) and "id" in item:
                index[(OverrideTargetType.ROB_ITEM_ASSESSMENT, str(item["id"]))] = item

    for item in measurement_payload:
        if isinstance(item, dict) and "id" in item:
            index[(OverrideTargetType.MEASUREMENT_PROPERTY_RESULT, str(item["id"]))] = item

    for item in synthesis_payload:
        if isinstance(item, dict) and "id" in item:
            index[(OverrideTargetType.SYNTHESIS_RESULT, str(item["id"]))] = item

    for item in grade_payload:
        if isinstance(item, dict) and "id" in item:
            index[(OverrideTargetType.GRADE_RESULT, str(item["id"]))] = item

    return index


def _apply_overrides(
    *,
    overrides: tuple[ReviewOverrideRequest, ...],
    target_index: dict[tuple[OverrideTargetType, str], dict[str, Any]],
    existing_override_count: int,
) -> tuple[ReviewerOverride, ...]:
    applied: list[ReviewerOverride] = []

    for offset, request in enumerate(overrides, start=1):
        key = (request.target_object_type, request.target_object_id)
        target = target_index.get(key)
        if target is None:
            msg = (
                "override target not found: "
                f"{request.target_object_type.value}:{request.target_object_id}"
            )
            raise ValueError(msg)

        field_spec = _allowed_field_spec(
            target_type=request.target_object_type,
            field_name=request.field_name,
        )
        if request.field_name not in target:
            msg = (
                "override field does not exist on target: "
                f"{request.target_object_type.value}:{request.target_object_id}:{request.field_name}"
            )
            raise ValueError(msg)

        previous_value = target[request.field_name]
        coerced_value = _coerce_override_value(
            raw_value=request.overridden_value,
            field_spec=field_spec,
        )
        target[request.field_name] = coerced_value

        created_at = request.created_at_utc or datetime.now(UTC)
        override = ReviewerOverride(
            id=_stable_id(
                "override",
                existing_override_count + offset,
                request.target_object_type.value,
                request.target_object_id,
                request.field_name,
                request.reviewer_id,
                request.reason,
                created_at.isoformat(),
            ),
            target_object_type=request.target_object_type.value,
            target_object_id=request.target_object_id,
            reviewer_id=request.reviewer_id,
            decision_status=request.decision_status,
            reason=request.reason,
            previous_value=_serialize_override_value(previous_value),
            overridden_value=_serialize_override_value(coerced_value),
            evidence_span_ids=list(request.evidence_span_ids),
            uncertainty_status=UncertaintyStatus.REVIEWER_REQUIRED,
            created_at_utc=created_at,
        )
        applied.append(override)

    return tuple(applied)


def _build_adjudications(
    *,
    requests: tuple[AdjudicationNoteRequest, ...],
    existing_note_count: int,
) -> tuple[ReviewerAdjudicationNote, ...]:
    notes: list[ReviewerAdjudicationNote] = []

    for offset, request in enumerate(requests, start=1):
        created_at = request.created_at_utc or datetime.now(UTC)
        note = ReviewerAdjudicationNote(
            id=_stable_id(
                "adjudication",
                existing_note_count + offset,
                request.decision_key.value,
                request.reviewer_id,
                created_at.isoformat(),
                request.reason,
                request.decision_value,
            ),
            decision_key=request.decision_key,
            decision_value=request.decision_value,
            reason=request.reason,
            reviewer_id=request.reviewer_id,
            related_object_type=request.related_object_type,
            related_object_id=request.related_object_id,
            evidence_span_ids=request.evidence_span_ids,
            created_at_utc=created_at,
        )
        notes.append(note)

    return tuple(notes)


def _allowed_field_spec(
    *,
    target_type: OverrideTargetType,
    field_name: str,
) -> _FieldSpec:
    specs = _ALLOWED_OVERRIDE_FIELDS.get(target_type)
    if specs is None or field_name not in specs:
        msg = "override field is not allowed for target type: " f"{target_type.value}:{field_name}"
        raise ValueError(msg)
    return specs[field_name]


def _coerce_override_value(*, raw_value: str, field_spec: _FieldSpec) -> Any:
    if field_spec.kind == "string":
        return raw_value

    if field_spec.kind == "boolean":
        lowered = raw_value.strip().lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
        msg = f"invalid boolean override value: {raw_value}"
        raise ValueError(msg)

    if field_spec.kind == "enum":
        assert field_spec.allowed_values is not None
        if raw_value not in field_spec.allowed_values:
            allowed = ", ".join(sorted(field_spec.allowed_values))
            msg = f"invalid enum override value '{raw_value}', allowed: [{allowed}]"
            raise ValueError(msg)
        return raw_value

    msg = f"unsupported override field kind: {field_spec.kind}"
    raise ValueError(msg)


def _serialize_override_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def _collect_pending_review_items(
    *,
    evidence_payload: dict[str, Any],
    rob_payload: list[dict[str, Any]],
    measurement_payload: list[dict[str, Any]],
    synthesis_payload: list[dict[str, Any]],
) -> tuple[PendingReviewItem, ...]:
    items: list[PendingReviewItem] = []

    items.extend(_pending_items_from_extraction(evidence_payload))
    items.extend(_pending_items_from_rob(rob_payload))
    items.extend(_pending_items_from_measurement(measurement_payload))
    items.extend(_pending_items_from_synthesis(synthesis_payload))

    dedup: dict[str, PendingReviewItem] = {}
    for item in items:
        dedup[item.id] = item

    return tuple(
        sorted(
            dedup.values(),
            key=lambda item: (item.source_stage, item.object_id, item.id),
        )
    )


def _pending_items_from_extraction(evidence_payload: dict[str, Any]) -> list[PendingReviewItem]:
    pending: list[PendingReviewItem] = []
    context_extraction = evidence_payload.get("context_extraction", {})

    for context_group_key in ("study_contexts", "instrument_contexts"):
        contexts = context_extraction.get(context_group_key, [])
        for context in contexts:
            if not isinstance(context, dict):
                continue
            for payload in context.values():
                if not isinstance(payload, dict):
                    continue
                if not {"id", "status", "field_name"}.issubset(payload.keys()):
                    continue

                status = str(payload.get("status"))
                if status not in {"ambiguous", "not_reported"}:
                    continue

                evidence_ids = _field_evidence_span_ids(payload)
                pending.append(
                    PendingReviewItem(
                        id=_stable_id("pending", "extract", payload.get("id"), status),
                        source_stage="extraction",
                        object_type="context_field",
                        object_id=str(payload["id"]),
                        reason=f"context field status is '{status}'",
                        evidence_span_ids=evidence_ids,
                    )
                )

    statistics = evidence_payload.get("statistics_extraction", {}).get("candidates", [])
    for candidate in statistics:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("evidence_source") != "unclear":
            continue
        candidate_id = candidate.get("id")
        if not candidate_id:
            continue
        pending.append(
            PendingReviewItem(
                id=_stable_id("pending", "extract", candidate_id, "unclear_source"),
                source_stage="extraction",
                object_type="statistic_candidate",
                object_id=str(candidate_id),
                reason="statistic evidence source is unclear",
                evidence_span_ids=tuple(candidate.get("evidence_span_ids", [])),
            )
        )

    return pending


def _field_evidence_span_ids(field_payload: dict[str, Any]) -> tuple[str, ...]:
    span_ids: set[str] = set()
    for candidate in field_payload.get("candidates", []):
        if isinstance(candidate, dict):
            for span_id in candidate.get("evidence_span_ids", []):
                span_ids.add(str(span_id))
    return tuple(sorted(span_ids))


def _pending_items_from_rob(rob_payload: list[dict[str, Any]]) -> list[PendingReviewItem]:
    pending: list[PendingReviewItem] = []

    for bundle in rob_payload:
        if not isinstance(bundle, dict):
            continue

        box = bundle.get("box_assessment")
        if isinstance(box, dict) and "id" in box and _is_reviewer_required(box):
            pending.append(
                PendingReviewItem(
                    id=_stable_id("pending", "rob", "box", box["id"]),
                    source_stage="rob",
                    object_type="rob_box_assessment",
                    object_id=str(box["id"]),
                    reason="RoB box assessment requires reviewer confirmation",
                    evidence_span_ids=tuple(box.get("evidence_span_ids", [])),
                )
            )

        for item in bundle.get("item_assessments", []):
            if not isinstance(item, dict) or "id" not in item:
                continue
            if not _is_reviewer_required(item):
                continue
            pending.append(
                PendingReviewItem(
                    id=_stable_id("pending", "rob", "item", item["id"]),
                    source_stage="rob",
                    object_type="rob_item_assessment",
                    object_id=str(item["id"]),
                    reason="RoB item assessment requires reviewer confirmation",
                    evidence_span_ids=tuple(item.get("evidence_span_ids", [])),
                )
            )

    return pending


def _pending_items_from_measurement(
    measurement_payload: list[dict[str, Any]],
) -> list[PendingReviewItem]:
    pending: list[PendingReviewItem] = []

    for item in measurement_payload:
        if not isinstance(item, dict) or "id" not in item:
            continue
        if not _is_reviewer_required(item):
            continue
        pending.append(
            PendingReviewItem(
                id=_stable_id("pending", "measurement", item["id"]),
                source_stage="measurement_rating",
                object_type="measurement_property_result",
                object_id=str(item["id"]),
                reason="measurement-property rating requires reviewer confirmation",
                evidence_span_ids=tuple(item.get("evidence_span_ids", [])),
            )
        )

    return pending


def _pending_items_from_synthesis(
    synthesis_payload: list[dict[str, Any]],
) -> list[PendingReviewItem]:
    pending: list[PendingReviewItem] = []

    for item in synthesis_payload:
        if not isinstance(item, dict) or "id" not in item:
            continue

        if item.get("inconsistent_findings") is True:
            pending.append(
                PendingReviewItem(
                    id=_stable_id("pending", "synthesis", item["id"], "inconsistent"),
                    source_stage="synthesis",
                    object_type="synthesis_result",
                    object_id=str(item["id"]),
                    reason="synthesis retains inconsistent findings requiring explanation",
                    evidence_span_ids=tuple(item.get("evidence_span_ids", [])),
                )
            )

        if item.get("requires_subgroup_explanation") is True:
            pending.append(
                PendingReviewItem(
                    id=_stable_id("pending", "synthesis", item["id"], "subgroup"),
                    source_stage="synthesis",
                    object_type="synthesis_result",
                    object_id=str(item["id"]),
                    reason="synthesis requires subgroup explanation adjudication",
                    evidence_span_ids=tuple(item.get("evidence_span_ids", [])),
                )
            )

    return pending


def _is_reviewer_required(payload: dict[str, Any]) -> bool:
    uncertainty = payload.get("uncertainty_status")
    reviewer_decision = payload.get("reviewer_decision_status")

    return (
        uncertainty != UncertaintyStatus.CERTAIN.value
        or reviewer_decision != ReviewerDecisionStatus.NOT_REQUIRED.value
    )


def _resolve_output_dir(
    *,
    source_dir: Path,
    out_dir: str | Path | None,
    review_status: ReviewStatus,
) -> Path:
    if out_dir is not None:
        return Path(out_dir).expanduser().resolve()

    suffix = "finalized_review" if review_status is ReviewStatus.FINALIZED else "reviewed"
    return (source_dir / suffix).resolve()


def _build_review_summary_markdown(
    *,
    review_state: ReviewState,
    measurement_payload: list[dict[str, Any]],
    synthesis_payload: list[dict[str, Any]],
    grade_payload: list[dict[str, Any]],
) -> str:
    title = (
        "# COSMIN Assistant Finalized Summary"
        if review_state.finalized
        else "# COSMIN Assistant Reviewed Summary"
    )
    lines = [
        title,
        "",
        f"- Review status: `{review_state.review_status.value}`",
        f"- Overrides applied in this run: `{review_state.overrides_applied_in_run}`",
        f"- Total overrides in history: `{review_state.overrides_total}`",
        f"- Adjudication notes added in this run: `{review_state.adjudication_notes_added_in_run}`",
        f"- Total adjudication notes in history: `{review_state.adjudication_notes_total}`",
        f"- Pending review items: `{len(review_state.pending_review_items)}`",
        "",
        "## Measurement Property Ratings",
    ]

    for result in measurement_payload:
        lines.append(
            f"- `{result.get('measurement_property')}`: `{result.get('computed_rating')}` "
            f"(rule `{result.get('rule_name')}`; "
            f"activation_status=`{result.get('activation_status')}`)"
        )

    lines.append("")
    lines.append("## Synthesis")
    for result in synthesis_payload:
        lines.append(
            f"- `{result.get('measurement_property')}`: `{result.get('summary_rating')}` "
            f"(total_n={result.get('total_sample_size')}; "
            f"activation_status=`{result.get('activation_status')}`)"
        )

    lines.append("")
    lines.append("## Modified GRADE")
    for result in grade_payload:
        if not bool(result.get("grade_executed", True)):
            lines.append(
                f"- `{result.get('measurement_property')}`: `not_graded` "
                f"(activation_status=`{result.get('activation_status')}`; "
                f"reason={result.get('explanation')})"
            )
            continue
        lines.append(
            f"- `{result.get('measurement_property')}`: `{result.get('starting_certainty')}` -> "
            f"`{result.get('final_certainty')}`"
        )

    if review_state.pending_review_items:
        lines.append("")
        lines.append("## Pending Review Items")
        for pending in review_state.pending_review_items:
            lines.append(
                f"- `{pending.source_stage}` `{pending.object_type}` `{pending.object_id}`: "
                f"{pending.reason}"
            )

    lines.append("")
    lines.append("_This report includes reviewer overrides and adjudication metadata._")
    return "\n".join(lines) + "\n"


def _build_per_study_dataframe(
    *,
    rob_payload: list[dict[str, Any]],
    measurement_payload: list[dict[str, Any]],
    grade_payload: list[dict[str, Any]],
) -> pd.DataFrame:
    box_by_property = {
        bundle.get("box_assessment", {})
        .get("measurement_property"): bundle.get("box_assessment", {})
        .get("box_rating", "")
        for bundle in rob_payload
        if isinstance(bundle, dict)
    }
    grade_by_property = {}
    for item in grade_payload:
        if not isinstance(item, dict):
            continue
        key = item.get("measurement_property")
        if bool(item.get("grade_executed", True)):
            grade_by_property[key] = item.get("final_certainty", "")
        else:
            grade_by_property[key] = "not_graded"

    rows: list[dict[str, str]] = []
    for result in measurement_payload:
        if not isinstance(result, dict):
            continue

        evidence_ids = result.get("evidence_span_ids", [])
        rows.append(
            {
                "study_id": str(result.get("study_id", "")),
                "instrument_id": str(result.get("instrument_id", "")),
                "measurement_property": str(result.get("measurement_property", "")),
                "box_rating": str(
                    box_by_property.get(str(result.get("measurement_property", "")), "")
                ),
                "study_level_rating": str(result.get("computed_rating", "")),
                "uncertainty_status": str(result.get("uncertainty_status", "")),
                "reviewer_decision_status": str(result.get("reviewer_decision_status", "")),
                "final_grade_certainty": str(
                    grade_by_property.get(str(result.get("measurement_property", "")), "")
                ),
                "evidence_span_ids": ",".join(str(span_id) for span_id in evidence_ids),
            }
        )

    return pd.DataFrame(rows)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _stable_id(prefix: str, *parts: object) -> str:
    serialized = "|".join(str(part) for part in parts)
    digest = hashlib.sha1(f"{prefix}|{serialized}".encode()).hexdigest()[:16]
    return f"{prefix}.{digest}"
