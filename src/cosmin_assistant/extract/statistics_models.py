"""Typed models for candidate statistic extraction with provenance."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field

from cosmin_assistant.models.base import ModelBase, NonEmptyText, StableId


class StatisticType(StrEnum):
    """Normalized statistic type names used for deterministic downstream scoring."""

    CRONBACH_ALPHA = "cronbach_alpha"
    KR20 = "kr20"
    ICC = "icc"
    KAPPA = "kappa"
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


class EvidenceSourceType(StrEnum):
    """Evidence source role for routing direct vs background vs interpretability evidence."""

    CURRENT_STUDY = "current_study"
    BACKGROUND_CITATION = "background_citation"
    INTERPRETABILITY_ONLY = "interpretability_only"
    UNCLEAR = "unclear"


class EvidenceRoutingBucket(StrEnum):
    """High-level extracted evidence separation buckets for audit-safe routing."""

    DIRECT_CURRENT_STUDY = "direct_current_study"
    BACKGROUND_CITATION = "background_citation"
    INTERPRETABILITY_SUPPORT = "interpretability_support"
    COMPARATOR_INSTRUMENT_CONTEXT = "comparator_instrument_context"


class MeasurementPropertyRoute(StrEnum):
    """Measurement-property buckets used for extraction-time routing support."""

    STRUCTURAL_VALIDITY = "structural_validity"
    INTERNAL_CONSISTENCY = "internal_consistency"
    RELIABILITY = "reliability"
    MEASUREMENT_ERROR_SUPPORT = "measurement_error_support"
    INTERPRETABILITY = "interpretability"
    RESPONSIVENESS = "responsiveness"
    HYPOTHESES_TESTING_FOR_CONSTRUCT_VALIDITY = "hypotheses_testing_for_construct_validity"


class EvidenceMethodLabel(StrEnum):
    """Method labels for MIC/MCID and related interpretability evidence."""

    ANCHOR_BASED = "anchor_based"
    DISTRIBUTION_BASED = "distribution_based"
    SEM_BASED = "sem_based"
    SDC_BASED = "sdc_based"
    LOA_BASED = "loa_based"
    MINIMAL_DETECTABLE_CHANGE = "minimal_detectable_change"
    TEST_RETEST_RELIABILITY = "test_retest_reliability"


class ResponsivenessHypothesisStatus(StrEnum):
    """Whether longitudinal responsiveness hypotheses were predefined."""

    PREDEFINED = "predefined"
    NOT_PREDEFINED = "not_predefined"
    NOT_REPORTED = "not_reported"


class StatisticCandidate(ModelBase):
    """One extracted statistic candidate with evidence provenance and subgroup context."""

    id: StableId
    statistic_type: StatisticType
    value_raw: NonEmptyText
    value_normalized: float | tuple[float, float] | str | None
    subgroup_label: str | None = None
    evidence_span_ids: Annotated[tuple[StableId, ...], Field(min_length=1)]
    surrounding_text: NonEmptyText
    instrument_name_hints: tuple[str, ...] = ()
    comparator_instrument_hints: tuple[str, ...] = ()
    evidence_source: EvidenceSourceType = EvidenceSourceType.CURRENT_STUDY
    supports_direct_assessment: bool = True
    measurement_property_routes: tuple[MeasurementPropertyRoute, ...] = ()
    method_labels: tuple[EvidenceMethodLabel, ...] = ()
    responsiveness_hypothesis_status: ResponsivenessHypothesisStatus | None = None


class ArticleStatisticsExtractionResult(ModelBase):
    """Article-level statistic candidate extraction output."""

    id: StableId
    article_id: StableId
    file_path: NonEmptyText
    candidates: tuple[StatisticCandidate, ...]
    direct_current_study_ids: tuple[StableId, ...] = ()
    background_citation_ids: tuple[StableId, ...] = ()
    interpretability_support_ids: tuple[StableId, ...] = ()
    comparator_instrument_context_ids: tuple[StableId, ...] = ()
