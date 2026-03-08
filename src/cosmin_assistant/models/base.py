"""Shared model utilities and constrained types."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

StableId = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9](?:[a-z0-9._:-]{0,127})$",
    ),
]

NonEmptyText = Annotated[str, StringConstraints(min_length=1)]

EvidenceSpanIdList = Annotated[list[StableId], Field(min_length=1)]


class ModelBase(BaseModel):
    """Strict immutable base model for deterministic JSON artifacts."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)
