"""Output builders and export interfaces."""

from cosmin_assistant.tables.docx_stub import DocxExporter, ProvisionalDocxExporter
from cosmin_assistant.tables.intermediate_models import (
    TableLegendEntry,
    Template5CharacteristicsRow,
    Template5CharacteristicsTable,
    Template7EvidenceRow,
    Template7EvidenceTable,
    Template7RowKind,
    Template8SummaryRow,
    Template8SummaryTable,
)
from cosmin_assistant.tables.output_builders import export_run_outputs
from cosmin_assistant.tables.table_builders import (
    build_template5_characteristics_table,
    build_template7_evidence_table,
    build_template8_summary_table,
    table_to_json_ready,
    template5_to_dataframe,
    template7_to_dataframe,
    template8_to_dataframe,
)

__all__ = [
    "DocxExporter",
    "ProvisionalDocxExporter",
    "TableLegendEntry",
    "Template5CharacteristicsRow",
    "Template5CharacteristicsTable",
    "Template7EvidenceRow",
    "Template7EvidenceTable",
    "Template7RowKind",
    "Template8SummaryRow",
    "Template8SummaryTable",
    "build_template5_characteristics_table",
    "build_template7_evidence_table",
    "build_template8_summary_table",
    "export_run_outputs",
    "table_to_json_ready",
    "template5_to_dataframe",
    "template7_to_dataframe",
    "template8_to_dataframe",
]
