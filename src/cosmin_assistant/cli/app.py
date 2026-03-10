"""Typer CLI entry point for provisional COSMIN assessment runs."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from cosmin_assistant.cli.pipeline import run_provisional_assessment
from cosmin_assistant.models import ProfileType
from cosmin_assistant.tables import export_run_outputs
from cosmin_assistant.utils import ensure_supported_python

app = typer.Typer(add_completion=False)

ArticleArgument = Annotated[
    Path,
    typer.Argument(
        ...,
        exists=True,
        readable=True,
        help="Parsed article markdown path.",
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
        help="Output directory for exported artifacts.",
    ),
]


@app.command()
def main(
    article: ArticleArgument,
    profile: ProfileOption = ProfileType.PROM,
    out: OutOption = Path("results"),
) -> None:
    """Run provisional parse -> extract -> RoB -> rating -> synthesis -> GRADE -> export."""

    try:
        ensure_supported_python()
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc

    try:
        run = run_provisional_assessment(article_path=article, profile_type=profile)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    try:
        output_paths = export_run_outputs(run=run, out_dir=out)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Completed provisional COSMIN assessment for {article}")
    for key in sorted(output_paths):
        typer.echo(f"{key}: {output_paths[key]}")


def run() -> None:
    """Console-script entry point."""

    ensure_supported_python()
    app()


if __name__ == "__main__":
    run()
