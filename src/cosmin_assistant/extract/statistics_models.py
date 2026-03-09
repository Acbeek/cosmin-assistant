"""Typed models for candidate statistic extraction with provenance."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field

from cosmin_assistant.models.base import ModelBase, NonEmptyText, StableId


class StatisticType(StrEnum):
    """Normalized statistic type names used for deterministic downstream scoring."""

    CRONBACH_ALPHA = "cronbach_alpha"
    ICC = "icc"
    WEIGHTED_KAPPA = "weighted_kappa"
    SEM = "sem"
    SDC = "sdc"
    LOA = "loa"
    MIC = "mic"
    CFI = "cfi"
    TLI = "tli"
    RMSEA = "rmsea"
    SRMR = "srmr"
    AUC = "auc"
    CORRELATION = "correlation"
    DIF_FINDING = "dif_finding"
    MEASUREMENT_INVARIANCE_FINDING = "measurement_invariance_finding"
    KNOWN_GROUPS_OR_COMPARATOR_RESULT = "known_groups_or_comparator_result"
    RESPONSIVENESS_RELATED_STATISTIC = "responsiveness_related_statistic"


class StatisticCandidate(ModelBase):
    """One extracted statistic candidate with evidence provenance and subgroup context."""

    id: StableId
    statistic_type: StatisticType
    value_raw: NonEmptyText
    value_normalized: float | tuple[float, float] | str | None
    subgroup_label: str | None = None
    evidence_span_ids: Annotated[tuple[StableId, ...], Field(min_length=1)]
    surrounding_text: NonEmptyText


class ArticleStatisticsExtractionResult(ModelBase):
    """Article-level statistic candidate extraction output."""

    id: StableId
    article_id: StableId
    file_path: NonEmptyText
    candidates: tuple[StatisticCandidate, ...]
