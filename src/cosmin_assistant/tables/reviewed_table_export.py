"""Thin post-review Template 7/8 export orchestration."""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path

from cosmin_assistant.tables.docx_tables import export_template7_docx, export_template8_docx
from cosmin_assistant.tables.reviewed_artifact_loader import load_reviewed_table_export_inputs
from cosmin_assistant.tables.table_builders import (
    build_template7_evidence_table,
    build_template8_summary_table,
    table_to_json_ready,
    template7_to_dataframe,
    template8_to_dataframe,
)


class TableTemplateSelection(StrEnum):
    """Template selection for reviewed table export."""

    TEMPLATE_7 = "7"
    TEMPLATE_8 = "8"
    ALL = "all"


def export_reviewed_tables(
    *,
    input_dir: str | Path,
    out_dir: str | Path | None = None,
    template: TableTemplateSelection = TableTemplateSelection.ALL,
    allow_provisional: bool = False,
) -> dict[str, str]:
    """Export template 7/8 JSON+CSV+DOCX from reviewed output artifacts."""

    loaded = load_reviewed_table_export_inputs(
        input_dir=input_dir,
        allow_provisional=allow_provisional,
    )
    destination = (
        Path(out_dir).expanduser().resolve() if out_dir is not None else loaded.input_dir / "tables"
    )
    destination.mkdir(parents=True, exist_ok=True)

    outputs: dict[str, str] = {}
    if template in (TableTemplateSelection.TEMPLATE_7, TableTemplateSelection.ALL):
        template7 = build_template7_evidence_table(
            instrument_contexts=loaded.instrument_contexts,
            rob_assessments=loaded.rob_assessments,
            measurement_results=loaded.measurement_results,
            synthesis_results=loaded.synthesis_results,
            grade_results=loaded.grade_results,
        )
        template7_json = destination / "template_7.json"
        template7_csv = destination / "template_7.csv"
        template7_docx = destination / "template_7.docx"
        template7_json.write_text(
            json.dumps(table_to_json_ready(template7), indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        template7_to_dataframe(template7).to_csv(template7_csv, index=False)
        export_template7_docx(table=template7, output_path=template7_docx)
        outputs["template_7_json"] = str(template7_json)
        outputs["template_7_csv"] = str(template7_csv)
        outputs["template_7_docx"] = str(template7_docx)

    if template in (TableTemplateSelection.TEMPLATE_8, TableTemplateSelection.ALL):
        template8 = build_template8_summary_table(
            instrument_contexts=loaded.instrument_contexts,
            synthesis_results=loaded.synthesis_results,
            grade_results=loaded.grade_results,
        )
        template8_json = destination / "template_8.json"
        template8_csv = destination / "template_8.csv"
        template8_docx = destination / "template_8.docx"
        template8_json.write_text(
            json.dumps(table_to_json_ready(template8), indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        template8_to_dataframe(template8).to_csv(template8_csv, index=False)
        export_template8_docx(table=template8, output_path=template8_docx)
        outputs["template_8_json"] = str(template8_json)
        outputs["template_8_csv"] = str(template8_csv)
        outputs["template_8_docx"] = str(template8_docx)

    return outputs
