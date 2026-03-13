"""Typer CLI entry point for post-review Template 7/8 exports."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from cosmin_assistant.tables.reviewed_table_export import (
    TableTemplateSelection,
    export_reviewed_tables,
)
from cosmin_assistant.utils import ensure_supported_python

app = typer.Typer(add_completion=False)

InputDirOption = Annotated[
    Path,
    typer.Option(
        ...,
        "--input-dir",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        help="Directory containing reviewed/finalized output artifacts.",
    ),
]
OutDirOption = Annotated[
    Path | None,
    typer.Option(
        "--out-dir",
        file_okay=False,
        dir_okay=True,
        writable=True,
        help="Destination directory for table exports (default: <input-dir>/tables).",
    ),
]
TemplateOption = Annotated[
    TableTemplateSelection,
    typer.Option(
        "--template",
        case_sensitive=False,
        help="Template selection: 7, 8, or all.",
    ),
]
AllowProvisionalOption = Annotated[
    bool,
    typer.Option(
        "--allow-provisional",
        help="Allow export when review_state.finalized is false.",
    ),
]


@app.command()
def main(
    input_dir: InputDirOption,
    out_dir: OutDirOption = None,
    template: TemplateOption = TableTemplateSelection.ALL,
    allow_provisional: AllowProvisionalOption = False,
) -> None:
    """Export COSMIN-style Template 7/8 artifacts from reviewed output directories."""

    try:
        ensure_supported_python()
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc

    try:
        output_paths = export_reviewed_tables(
            input_dir=input_dir,
            out_dir=out_dir,
            template=template,
            allow_provisional=allow_provisional,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"Completed table export from {input_dir}")
    for key in sorted(output_paths):
        typer.echo(f"{key}: {output_paths[key]}")


def run_tables() -> None:
    """Console-script entry point for reviewed table export CLI."""

    ensure_supported_python()
    app()


if __name__ == "__main__":
    run_tables()
