"""Intermediate table models for COSMIN-style exports.

These models intentionally stay independent from any rendering backend
(for example DOCX templates). They represent structured table objects
that can be serialized to JSON and converted to CSV-ready data frames.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from cosmin_assistant.models import ModelBase, NonEmptyText, StableId


class TableLegendEntry(ModelBase):
    """Legend entry for one key/symbol used in a table."""

    key: NonEmptyText
    description: NonEmptyText


class Template7RowKind(StrEnum):
    """Row type for template 7 equivalent tables."""

    STUDY = "study"
    SUMMARY = "summary"


class Template5CharacteristicsRow(ModelBase):
    """Template 5 equivalent row: study characteristics by instrument unit."""

    id: StableId
    instrument_name: NonEmptyText
    instrument_version: str | None = None
    subscale: str | None = None
    study_id: StableId
    study_order_within_instrument: int = Field(ge=1)
    is_additional_study_row: bool
    study_design: str | None = None
    target_population: str | None = None
    language: str | None = None
    country: str | None = None
    enrollment_n: int | None = Field(default=None, ge=0)
    analyzed_n: int | None = Field(default=None, ge=0)
    limb_level_n: int | None = Field(default=None, ge=0)
    follow_up_schedule: str | None = None
    measurement_properties_mentioned: str | None = None


class Template5CharacteristicsTable(ModelBase):
    """Template 5 equivalent intermediate table object."""

    id: StableId
    template_code: NonEmptyText = "template_5"
    title: NonEmptyText = "Characteristics of studies on other measurement properties"
    rows: tuple[Template5CharacteristicsRow, ...]
    legends: tuple[TableLegendEntry, ...]


class Template7EvidenceRow(ModelBase):
    """Template 7 equivalent row with study and summary fields."""

    id: StableId
    row_kind: Template7RowKind
    instrument_name: NonEmptyText
    instrument_version: str | None = None
    subscale: str | None = None
    measurement_property: NonEmptyText
    study_id: StableId | None = None
    study_order_within_instrument_property: int | None = Field(default=None, ge=1)
    is_additional_study_row: bool | None = None
    per_study_rob: str | None = None
    per_study_result: str | None = None
    study_rating: str | None = None
    summarized_result: str | None = None
    overall_rating: str | None = None
    certainty_of_evidence: str | None = None
    total_sample_size: int | None = Field(default=None, ge=0)


class Template7EvidenceTable(ModelBase):
    """Template 7 equivalent intermediate table object."""

    id: StableId
    template_code: NonEmptyText = "template_7"
    title: NonEmptyText = (
        "Per-study RoB, study results, synthesis summary, and certainty of evidence"
    )
    rows: tuple[Template7EvidenceRow, ...]
    legends: tuple[TableLegendEntry, ...]


class Template8SummaryRow(ModelBase):
    """Template 8 equivalent row: summary of findings per instrument/property."""

    id: StableId
    instrument_name: NonEmptyText
    instrument_version: str | None = None
    subscale: str | None = None
    measurement_property: NonEmptyText
    summarized_result: str | None = None
    overall_rating: str | None = None
    certainty_of_evidence: str | None = None
    total_sample_size: int | None = Field(default=None, ge=0)
    inconsistent_findings: bool | None = None


class Template8SummaryTable(ModelBase):
    """Template 8 equivalent intermediate table object."""

    id: StableId
    template_code: NonEmptyText = "template_8"
    title: NonEmptyText = "Summary of findings across measurement properties"
    rows: tuple[Template8SummaryRow, ...]
    legends: tuple[TableLegendEntry, ...]
