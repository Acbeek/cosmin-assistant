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
        }


def discover_markdown_articles(*, input_dir: Path, recursive: bool = True) -> tuple[Path, ...]:
    """Discover markdown article files in deterministic sorted order."""

    pattern = "**/*.md" if recursive else "*.md"
    discovered = [
        path
        for path in input_dir.glob(pattern)
        if path.is_file() and not path.name.startswith(".")
    ]
    return tuple(sorted(path.resolve() for path in discovered))


def run_batch_assessment(
    *,
    input_dir: Path,
    out_dir: Path,
    profile_type: ProfileType,
    recursive: bool = True,
) -> dict[str, str]:
    """Run the frozen single-paper pipeline once per discovered article."""

    articles = discover_markdown_articles(input_dir=input_dir, recursive=recursive)
    if not articles:
        msg = f"No markdown files were discovered in {input_dir}."
        raise ValueError(msg)

    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[BatchSummaryRow] = []

    for article_path in articles:
        run = run_provisional_assessment(article_path=article_path, profile_type=profile_type)
        article_out_dir = out_dir / _article_output_dir_name(
            article_path=article_path,
            input_root=input_dir.resolve(),
        )
        export_run_outputs(run=run, out_dir=article_out_dir)
        rows.append(
            _build_batch_summary_row(
                run=run,
                article_path=article_path,
                article_out_dir=article_out_dir,
            )
        )

    summary_csv = out_dir / "batch_summary.csv"
    summary_json = out_dir / "batch_summary.json"
    _write_batch_summary_csv(summary_csv, rows)
    _write_batch_summary_json(summary_json, rows)

    return {
        "batch_output_root": str(out_dir),
        "batch_summary_csv": str(summary_csv),
        "batch_summary_json": str(summary_json),
        "articles_processed": str(len(rows)),
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
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_dict())


def _write_batch_summary_json(path: Path, rows: list[BatchSummaryRow]) -> None:
    payload = [row.to_dict() for row in rows]
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


@app.command()
def main(
    input_dir: InputDirArgument,
    profile: ProfileOption = ProfileType.PROM,
    out: OutOption = Path("results/batch"),
    recursive: RecursiveOption = True,
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
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"Completed provisional batch COSMIN assessment for {input_dir}")
    for key in sorted(outputs):
        typer.echo(f"{key}: {outputs[key]}")


def run_batch() -> None:
    """Console-script entry point for batch assessment CLI."""

    ensure_supported_python()
    app()


if __name__ == "__main__":
    run_batch()
