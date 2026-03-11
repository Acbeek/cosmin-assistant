"""Typer CLI entry point for thin batch orchestration over markdown articles."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

from cosmin_assistant.cli.pipeline import ProvisionalAssessmentRun, run_provisional_assessment
from cosmin_assistant.extract import InstrumentContextRole
from cosmin_assistant.models import ProfileType, PropertyActivationStatus
from cosmin_assistant.tables import export_run_outputs
from cosmin_assistant.utils import ensure_supported_python

app = typer.Typer(add_completion=False)

InputDirArgument = Annotated[
    Path,
    typer.Argument(
        ...,
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        help="Directory containing parsed markdown articles.",
    ),
]
ProfileOption = Annotated[
    ProfileType,
    typer.Option("--profile", help="Instrument profile."),
]
OutOption = Annotated[
    Path,
    typer.Option(
        "--out",
        file_okay=False,
        dir_okay=True,
        writable=True,
        help="Output root directory for per-article artifacts.",
    ),
]
RecursiveOption = Annotated[
    bool,
    typer.Option(
        "--recursive/--no-recursive",
        help="Discover markdown files recursively from the input directory.",
    ),
]
ContinueOnErrorOption = Annotated[
    bool,
    typer.Option(
        "--continue-on-error/--fail-fast",
        help=(
            "Continue processing remaining markdown files when one article fails. "
            "If fail-fast is selected, processing stops after first failure."
        ),
    ),
]

_KEY_ACTIVE_STATUSES: tuple[PropertyActivationStatus, ...] = (
    PropertyActivationStatus.DIRECT_CURRENT_STUDY_EVIDENCE,
    PropertyActivationStatus.MEASUREMENT_ERROR_SUPPORT_ONLY,
    PropertyActivationStatus.INTERPRETABILITY_ONLY,
)


@dataclass(frozen=True)
class BatchSummaryRow:
    """Concise per-article batch summary record."""

    article_name: str
    article_path: str
    output_dir: str
    target_instruments: str
    study_intent: str
    key_active_properties: str
    review_status: str
    run_status: str
    error_message: str

    def to_dict(self) -> dict[str, str]:
        """Serialize to a CSV/JSON-friendly dictionary."""

        return {
            "article_name": self.article_name,
            "article_path": self.article_path,
            "output_dir": self.output_dir,
            "target_instruments": self.target_instruments,
            "study_intent": self.study_intent,
            "key_active_properties": self.key_active_properties,
            "review_status": self.review_status,
            "run_status": self.run_status,
            "error_message": self.error_message,
        }


def discover_markdown_articles(*, input_dir: Path, recursive: bool = True) -> tuple[Path, ...]:
    """Discover markdown article files in deterministic sorted order."""

    pattern = "**/*.md" if recursive else "*.md"
    discovered = [
        path for path in input_dir.glob(pattern) if path.is_file() and not path.name.startswith(".")
    ]
    return tuple(sorted(path.resolve() for path in discovered))


def run_batch_assessment(
    *,
    input_dir: Path,
    out_dir: Path,
    profile_type: ProfileType,
    recursive: bool = True,
    continue_on_error: bool = True,
) -> dict[str, str]:
    """Run the frozen single-paper pipeline once per discovered article."""

    articles = discover_markdown_articles(input_dir=input_dir, recursive=recursive)
    if not articles:
        msg = f"No markdown files were discovered in {input_dir}."
        raise ValueError(msg)

    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[BatchSummaryRow] = []
    failed_count = 0
    used_output_dir_names: set[str] = set()

    for article_path in articles:
        article_out_name = _allocate_unique_output_dir_name(
            article_path=article_path,
            input_root=input_dir.resolve(),
            used_names=used_output_dir_names,
        )
        article_out_dir = out_dir / article_out_name
        try:
            run = run_provisional_assessment(article_path=article_path, profile_type=profile_type)
            export_run_outputs(run=run, out_dir=article_out_dir)
            rows.append(
                _build_batch_summary_row(
                    run=run,
                    article_path=article_path,
                    article_out_dir=article_out_dir,
                )
            )
        except Exception as exc:
            failed_count += 1
            error_message = _format_batch_error(exc)
            article_out_dir.mkdir(parents=True, exist_ok=True)
            _write_batch_error_json(
                article_path=article_path,
                article_out_dir=article_out_dir,
                error_message=error_message,
            )
            rows.append(
                _build_failed_batch_summary_row(
                    article_path=article_path,
                    article_out_dir=article_out_dir,
                    error_message=error_message,
                )
            )
            if not continue_on_error:
                break

    summary_csv = out_dir / "batch_summary.csv"
    summary_json = out_dir / "batch_summary.json"
    _write_batch_summary_csv(summary_csv, rows)
    _write_batch_summary_json(summary_json, rows)

    return {
        "batch_output_root": str(out_dir),
        "batch_summary_csv": str(summary_csv),
        "batch_summary_json": str(summary_json),
        "articles_discovered": str(len(articles)),
        "articles_processed": str(len(rows)),
        "articles_succeeded": str(len(rows) - failed_count),
        "articles_failed": str(failed_count),
        "continue_on_error": str(continue_on_error).lower(),
        "exit_code": "1" if failed_count > 0 else "0",
    }


def _article_output_dir_name(*, article_path: Path, input_root: Path) -> str:
    try:
        relative = article_path.resolve().relative_to(input_root)
        relative_stem = relative.with_suffix("")
    except ValueError:
        relative_stem = Path(article_path.stem)

    slug_source = "__".join(relative_stem.parts) or article_path.stem
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", slug_source).strip("._")
    digest = hashlib.sha1(str(article_path.resolve()).encode("utf-8")).hexdigest()[:8]
    return f"{slug}_{digest}"


def _allocate_unique_output_dir_name(
    *,
    article_path: Path,
    input_root: Path,
    used_names: set[str],
) -> str:
    """Allocate a deterministic collision-safe output directory name."""

    base = _article_output_dir_name(article_path=article_path, input_root=input_root)
    if base not in used_names:
        used_names.add(base)
        return base

    suffix = 1
    while True:
        candidate = f"{base}__dup{suffix:02d}"
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
        suffix += 1


def _build_batch_summary_row(
    *,
    run: ProvisionalAssessmentRun,
    article_path: Path,
    article_out_dir: Path,
) -> BatchSummaryRow:
    instrument_name_by_id = {
        context.instrument_id: (
            _first_text_candidate(context.instrument_name) or context.instrument_id
        )
        for context in run.context_extraction.instrument_contexts
    }

    target_instruments = sorted(
        {
            _first_text_candidate(context.instrument_name) or "unknown"
            for context in run.context_extraction.instrument_contexts
            if context.instrument_role
            in (
                InstrumentContextRole.TARGET_UNDER_APPRAISAL,
                InstrumentContextRole.CO_PRIMARY_OUTCOME_INSTRUMENT,
            )
        }
    )
    if not target_instruments and run.context_extraction.target_instrument_id:
        target_instruments = [
            instrument_name_by_id.get(run.context_extraction.target_instrument_id, "unknown")
        ]

    study_intent = run.context_extraction.study_contexts[0].study_intent.value
    key_active = sorted(
        {
            (
                f"{instrument_name_by_id.get(result.instrument_id, result.instrument_id)}:"
                f"{result.measurement_property}[{result.activation_status.value}]"
            )
            for result in run.measurement_property_results
            if result.activation_status in _KEY_ACTIVE_STATUSES
        }
    )

    return BatchSummaryRow(
        article_name=article_path.name,
        article_path=str(article_path.resolve()),
        output_dir=str(article_out_dir.resolve()),
        target_instruments="; ".join(target_instruments),
        study_intent=study_intent,
        key_active_properties="; ".join(key_active),
        review_status="provisional",
        run_status="success",
        error_message="",
    )


def _build_failed_batch_summary_row(
    *,
    article_path: Path,
    article_out_dir: Path,
    error_message: str,
) -> BatchSummaryRow:
    return BatchSummaryRow(
        article_name=article_path.name,
        article_path=str(article_path.resolve()),
        output_dir=str(article_out_dir.resolve()),
        target_instruments="",
        study_intent="",
        key_active_properties="",
        review_status="not_generated",
        run_status="failed",
        error_message=error_message,
    )


def _first_text_candidate(field: object) -> str | None:
    candidates = getattr(field, "candidates", None)
    if not candidates:
        return None
    first = candidates[0]
    normalized = getattr(first, "normalized_value", None)
    if isinstance(normalized, str):
        return normalized
    return None


def _write_batch_summary_csv(path: Path, rows: list[BatchSummaryRow]) -> None:
    fieldnames = [
        "article_name",
        "article_path",
        "output_dir",
        "target_instruments",
        "study_intent",
        "key_active_properties",
        "review_status",
        "run_status",
        "error_message",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_dict())


def _write_batch_summary_json(path: Path, rows: list[BatchSummaryRow]) -> None:
    payload = [row.to_dict() for row in rows]
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_batch_error_json(
    *,
    article_path: Path,
    article_out_dir: Path,
    error_message: str,
) -> None:
    payload = {
        "article_name": article_path.name,
        "article_path": str(article_path.resolve()),
        "error_message": error_message,
        "run_status": "failed",
    }
    (article_out_dir / "batch_error.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _format_batch_error(exc: Exception) -> str:
    detail = str(exc).strip()
    if detail:
        return f"{exc.__class__.__name__}: {detail}"
    return exc.__class__.__name__


@app.command()
def main(
    input_dir: InputDirArgument,
    profile: ProfileOption = ProfileType.PROM,
    out: OutOption = Path("results/batch"),
    recursive: RecursiveOption = True,
    continue_on_error: ContinueOnErrorOption = True,
) -> None:
    """Run provisional assessment once per markdown file in a directory."""

    try:
        ensure_supported_python()
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc

    try:
        outputs = run_batch_assessment(
            input_dir=input_dir,
            out_dir=out,
            profile_type=profile,
            recursive=recursive,
            continue_on_error=continue_on_error,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"Completed provisional batch COSMIN assessment for {input_dir}")
    for key in sorted(outputs):
        typer.echo(f"{key}: {outputs[key]}")
    if int(outputs["articles_failed"]) > 0:
        raise typer.Exit(code=1)


def run_batch() -> None:
    """Console-script entry point for batch assessment CLI."""

    ensure_supported_python()
    app()


if __name__ == "__main__":
    run_batch()
