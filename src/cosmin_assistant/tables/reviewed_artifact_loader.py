"""Load reviewed/finalized artifact directories for table export."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from pydantic import ValidationError

from cosmin_assistant.cosmin_rob import BoxAssessmentBundle
from cosmin_assistant.extract import (
    ArticleContextExtractionResult,
    InstrumentContextExtractionResult,
)
from cosmin_assistant.grade import ModifiedGradeResult
from cosmin_assistant.measurement_rating import MeasurementPropertyRatingResult
from cosmin_assistant.models import ModelBase
from cosmin_assistant.review import ReviewState
from cosmin_assistant.synthesize import SynthesisAggregateResult

_ARTIFACT_BASENAMES: dict[str, str] = {
    "evidence_json": "evidence.json",
    "rob_assessment_json": "rob_assessment.json",
    "measurement_property_results_json": "measurement_property_results.json",
    "synthesis_json": "synthesis.json",
    "grade_json": "grade.json",
    "review_state_json": "review_state.json",
    "run_manifest_json": "run_manifest.json",
}
_REQUIRED_ARTIFACT_KEYS: tuple[str, ...] = (
    "evidence_json",
    "rob_assessment_json",
    "measurement_property_results_json",
    "synthesis_json",
    "grade_json",
    "review_state_json",
)
_TABLE_MANIFEST_KEYS: tuple[str, str] = (
    "artifact_filenames_prefixed",
    "artifact_filenames_legacy",
)
_ModelT = TypeVar("_ModelT", bound=ModelBase)


@dataclass(frozen=True)
class ReviewedTableExportInputs:
    """Typed payload required by template 7/8 builders."""

    input_dir: Path
    resolved_paths: dict[str, Path]
    review_state: ReviewState
    instrument_contexts: tuple[InstrumentContextExtractionResult, ...]
    rob_assessments: tuple[BoxAssessmentBundle, ...]
    measurement_results: tuple[MeasurementPropertyRatingResult, ...]
    synthesis_results: tuple[SynthesisAggregateResult, ...]
    grade_results: tuple[ModifiedGradeResult, ...]


def load_reviewed_table_export_inputs(
    *,
    input_dir: str | Path,
    allow_provisional: bool = False,
) -> ReviewedTableExportInputs:
    """Load typed table-export inputs from reviewed/provisional artifacts."""

    root = Path(input_dir).expanduser().resolve()
    manifest_path, manifest_payload = _load_manifest_if_present(root)
    resolved_paths = _resolve_artifact_paths(
        root=root,
        manifest_payload=manifest_payload,
    )
    if manifest_path is not None:
        resolved_paths["run_manifest_json"] = manifest_path

    review_state_payload = _read_required_json_object(
        path=resolved_paths["review_state_json"],
        artifact_name=_ARTIFACT_BASENAMES["review_state_json"],
    )
    review_state = _validate_model(
        payload=review_state_payload,
        model_type=ReviewState,
        artifact_name=_ARTIFACT_BASENAMES["review_state_json"],
    )
    if not review_state.finalized and not allow_provisional:
        msg = (
            "review_state.json indicates provisional outputs (finalized=false). "
            "Finalize review outputs first or pass --allow-provisional."
        )
        raise ValueError(msg)

    evidence_payload = _read_required_json_object(
        path=resolved_paths["evidence_json"],
        artifact_name=_ARTIFACT_BASENAMES["evidence_json"],
    )
    context_payload = evidence_payload.get("context_extraction")
    if not isinstance(context_payload, dict):
        msg = "evidence.json is missing context_extraction required for table export."
        raise ValueError(msg)
    context_extraction = _validate_model(
        payload=context_payload,
        model_type=ArticleContextExtractionResult,
        artifact_name="evidence.context_extraction",
    )

    rob_payload = _read_required_json_list(
        path=resolved_paths["rob_assessment_json"],
        artifact_name=_ARTIFACT_BASENAMES["rob_assessment_json"],
    )
    measurement_payload = _read_required_json_list(
        path=resolved_paths["measurement_property_results_json"],
        artifact_name=_ARTIFACT_BASENAMES["measurement_property_results_json"],
    )
    synthesis_payload = _read_required_json_list(
        path=resolved_paths["synthesis_json"],
        artifact_name=_ARTIFACT_BASENAMES["synthesis_json"],
    )
    grade_payload = _read_required_json_list(
        path=resolved_paths["grade_json"],
        artifact_name=_ARTIFACT_BASENAMES["grade_json"],
    )

    return ReviewedTableExportInputs(
        input_dir=root,
        resolved_paths=resolved_paths,
        review_state=review_state,
        instrument_contexts=context_extraction.instrument_contexts,
        rob_assessments=_validate_model_rows(
            payload=rob_payload,
            model_type=BoxAssessmentBundle,
            artifact_name=_ARTIFACT_BASENAMES["rob_assessment_json"],
        ),
        measurement_results=_validate_model_rows(
            payload=measurement_payload,
            model_type=MeasurementPropertyRatingResult,
            artifact_name=_ARTIFACT_BASENAMES["measurement_property_results_json"],
        ),
        synthesis_results=_validate_model_rows(
            payload=synthesis_payload,
            model_type=SynthesisAggregateResult,
            artifact_name=_ARTIFACT_BASENAMES["synthesis_json"],
        ),
        grade_results=_validate_model_rows(
            payload=grade_payload,
            model_type=ModifiedGradeResult,
            artifact_name=_ARTIFACT_BASENAMES["grade_json"],
        ),
    )


def _resolve_artifact_paths(
    *,
    root: Path,
    manifest_payload: dict[str, Any] | None,
) -> dict[str, Path]:
    resolved: dict[str, Path] = {}
    for artifact_key in _REQUIRED_ARTIFACT_KEYS:
        if manifest_payload is not None:
            path = _resolve_with_manifest(
                root=root,
                artifact_key=artifact_key,
                manifest_payload=manifest_payload,
            )
        else:
            path = _resolve_without_manifest(root=root, artifact_key=artifact_key)
        resolved[artifact_key] = path
    return resolved


def _load_manifest_if_present(root: Path) -> tuple[Path | None, dict[str, Any] | None]:
    legacy_manifest = root / _ARTIFACT_BASENAMES["run_manifest_json"]
    if legacy_manifest.exists():
        payload = _read_required_json_object(
            path=legacy_manifest,
            artifact_name=_ARTIFACT_BASENAMES["run_manifest_json"],
        )
        return legacy_manifest, payload

    prefixed_candidates = sorted(root.glob("*__run_manifest.json"))
    if not prefixed_candidates:
        return None, None
    if len(prefixed_candidates) > 1:
        names = ", ".join(candidate.name for candidate in prefixed_candidates)
        msg = (
            "multiple prefixed run manifests were found; provide a single-run directory: "
            f"{names}"
        )
        raise ValueError(msg)

    manifest_path = prefixed_candidates[0]
    payload = _read_required_json_object(
        path=manifest_path,
        artifact_name=_ARTIFACT_BASENAMES["run_manifest_json"],
    )
    return manifest_path, payload


def _resolve_with_manifest(
    *,
    root: Path,
    artifact_key: str,
    manifest_payload: dict[str, Any],
) -> Path:
    basename = _ARTIFACT_BASENAMES[artifact_key]
    candidates: list[Path] = []

    for section_key in _TABLE_MANIFEST_KEYS:
        section = manifest_payload.get(section_key)
        if isinstance(section, dict):
            candidate_name = section.get(artifact_key)
            if isinstance(candidate_name, str) and candidate_name.strip():
                candidates.append(root / candidate_name)

    artifact_prefix = manifest_payload.get("artifact_prefix")
    if isinstance(artifact_prefix, str) and artifact_prefix.strip():
        candidates.append(root / f"{artifact_prefix}__{basename}")
    candidates.append(root / basename)

    deduped_candidates = _dedupe_paths(candidates)
    for candidate in deduped_candidates:
        if candidate.exists():
            return candidate

    attempted = ", ".join(path.name for path in deduped_candidates)
    msg = f"required artifact '{basename}' was not found (tried: {attempted})."
    raise ValueError(msg)


def _resolve_without_manifest(*, root: Path, artifact_key: str) -> Path:
    basename = _ARTIFACT_BASENAMES[artifact_key]
    legacy_path = root / basename
    if legacy_path.exists():
        return legacy_path

    prefixed_candidates = sorted(root.glob(f"*__{basename}"))
    if len(prefixed_candidates) == 1:
        return prefixed_candidates[0]
    if len(prefixed_candidates) > 1:
        names = ", ".join(candidate.name for candidate in prefixed_candidates)
        msg = (
            f"required artifact '{basename}' is ambiguous; multiple prefixed files found: "
            f"{names}. Include run_manifest.json or use a single-run directory."
        )
        raise ValueError(msg)

    msg = f"required artifact file is missing: {legacy_path}"
    raise ValueError(msg)


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)
    return unique


def _read_required_json_object(*, path: Path, artifact_name: str) -> dict[str, Any]:
    payload = _read_json(path=path, artifact_name=artifact_name)
    if not isinstance(payload, dict):
        msg = f"{artifact_name} must contain a JSON object payload."
        raise ValueError(msg)
    return payload


def _read_required_json_list(*, path: Path, artifact_name: str) -> list[Any]:
    payload = _read_json(path=path, artifact_name=artifact_name)
    if not isinstance(payload, list):
        msg = f"{artifact_name} must contain a JSON array payload."
        raise ValueError(msg)
    return payload


def _read_json(*, path: Path, artifact_name: str) -> Any:
    if not path.exists():
        msg = f"required artifact file is missing: {path}"
        raise ValueError(msg)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        msg = f"{artifact_name} is not valid JSON: {path}"
        raise ValueError(msg) from exc


def _validate_model(
    *,
    payload: object,
    model_type: type[_ModelT],
    artifact_name: str,
) -> _ModelT:
    try:
        return model_type.model_validate(payload)
    except ValidationError as exc:
        msg = f"{artifact_name} did not match expected schema: {exc}"
        raise ValueError(msg) from exc


def _validate_model_rows(
    *,
    payload: list[Any],
    model_type: type[_ModelT],
    artifact_name: str,
) -> tuple[_ModelT, ...]:
    rows: list[_ModelT] = []
    for index, item in enumerate(payload, start=1):
        try:
            rows.append(model_type.model_validate(item))
        except ValidationError as exc:
            msg = (
                f"{artifact_name} row {index} did not match expected schema "
                f"({model_type.__name__}): {exc}"
            )
            raise ValueError(msg) from exc
    return tuple(rows)
