"""Typer CLI entry point for reviewer override application."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from cosmin_assistant.cli.workflow_hints import (
    default_metadata_review_summary_path,
    default_review_output_dir,
    handoff_lines,
    metadata_path_for_run_dir,
    shell_command,
)
from cosmin_assistant.review import apply_review_request_file
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
        help="Directory containing provisional JSON outputs.",
    ),
]
ReviewFileOption = Annotated[
    Path,
    typer.Option(
        ...,
        "--review-file",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="YAML/JSON review request bundle with overrides and adjudication notes; not the metadata YAML.",
    ),
]
OutOption = Annotated[
    Path | None,
    typer.Option(
        file_okay=False,
        dir_okay=True,
        writable=True,
        help="Output directory for reviewed artifacts (default: <input>/finalized_review).",
    ),
]
FinalizeOption = Annotated[
    bool,
    typer.Option(
        "--finalize/--keep-provisional",
        help="Mark reviewed output set as finalized or provisional.",
    ),
]


@app.command()
def main(
    provisional_dir: InputDirArgument,
    review_file: ReviewFileOption,
    out: OutOption = None,
    finalize: FinalizeOption = True,
) -> None:
    """Apply reviewer overrides to provisional COSMIN outputs."""

    try:
        ensure_supported_python()
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc

    try:
        output_paths = apply_review_request_file(
            provisional_dir=provisional_dir,
            review_file=review_file,
            out_dir=out,
            finalize=finalize,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"Completed reviewer override application for {provisional_dir}")
    for key in sorted(output_paths):
        typer.echo(f"{key}: {output_paths[key]}")

    reviewed_dir = out if out is not None else default_review_output_dir(
        provisional_dir=provisional_dir,
        finalize=finalize,
    )
    metadata_path = metadata_path_for_run_dir(run_dir=provisional_dir)
    summary_path = default_metadata_review_summary_path(
        run_dir=reviewed_dir,
        finalized=finalize,
    )
    for line in handoff_lines(
        f"reviewed_run_dir: {reviewed_dir}",
        f"metadata_file_default: {metadata_path}",
        f"metadata_review_summary: {summary_path}",
        "next: "
        + shell_command(
            "cosmin-metadata",
            "review",
            "--metadata",
            metadata_path,
            "--run-dir",
            reviewed_dir,
            "--json",
            "--report-out",
            summary_path,
        ),
    ):
        typer.echo(line)


def run_review() -> None:
    """Console-script entry point for review override CLI."""

    ensure_supported_python()
    app()


if __name__ == "__main__":
    run_review()
