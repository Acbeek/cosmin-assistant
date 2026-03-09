"""Typer CLI entry point for reviewer override application."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from cosmin_assistant.review import apply_review_request_file

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
        help="YAML/JSON file with overrides and adjudication notes.",
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


def run_review() -> None:
    """Console-script entry point for review override CLI."""

    app()


if __name__ == "__main__":
    run_review()
