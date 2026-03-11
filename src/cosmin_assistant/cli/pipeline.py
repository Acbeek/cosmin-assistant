"""Provisional end-to-end assessment pipeline orchestration."""

from __future__ import annotations

import hashlib
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cosmin_assistant.cli.property_activation import (
    STEP6_PROM_ITEM_BASED_PROPERTIES,
    PropertyActivationDecision,
    candidate_source_flags,
    merged_candidate_evidence,
    stable_activation_id,
)
from cosmin_assistant.cosmin_rob import (
    BOX_3_ITEM_CODES,
    BOX_4_ITEM_CODES,
    BOX_5_ITEM_CODES,
    BOX_6_ITEM_CODES,
    BOX_7_ITEM_CODES,
    BOX_8_ITEM_CODES,
    BOX_9_ITEM_CODES,
    BOX_10_ITEM_CODES,
    BoxAssessmentBundle,
    BoxItemInput,
    assess_box3_structural_validity,
    assess_box4_internal_consistency,
    assess_box5_cross_cultural_validity_measurement_invariance,
    assess_box6_reliability,
    assess_box7_measurement_error,
    assess_box8_criterion_validity,
    assess_box9_hypotheses_testing_for_construct_validity,
    assess_box10_responsiveness,
)
from cosmin_assistant.extract import (
    ArticleContextExtractionResult,
    ArticleStatisticsExtractionResult,
    ContextFieldExtraction,
    EvidenceMethodLabel,
    EvidenceSourceType,
    FieldDetectionStatus,
    InstrumentContextExtractionResult,
    InstrumentContextRole,
    MeasurementPropertyRoute,
    ParsedMarkdownDocument,
    ResponsivenessHypothesisStatus,
    SampleSizeRole,
    StatisticCandidate,
    StatisticType,
    StudyContextExtractionResult,
    StudyIntent,
    extract_context_from_parsed_document,
    extract_statistics_from_parsed_document,
    parse_markdown_file,
)
from cosmin_assistant.grade import (
    DomainDowngradeInput,
    DowngradeSeverity,
    ModifiedGradeDomain,
    ModifiedGradeResult,
    apply_modified_grade,
)
from cosmin_assistant.measurement_rating import (
    MEASUREMENT_PROPERTY_CONSTRUCT_VALIDITY,
    MEASUREMENT_PROPERTY_CRITERION_VALIDITY,
    MEASUREMENT_PROPERTY_CROSS_CULTURAL_VALIDITY,
    MEASUREMENT_PROPERTY_INTERNAL_CONSISTENCY,
    MEASUREMENT_PROPERTY_MEASUREMENT_ERROR,
    MEASUREMENT_PROPERTY_RELIABILITY,
    MEASUREMENT_PROPERTY_RESPONSIVENESS,
    MEASUREMENT_PROPERTY_STRUCTURAL_VALIDITY,
    REQUIRED_GOLD_STANDARD_PREREQUISITE_NAME,
    REQUIRED_HYPOTHESES_PREREQUISITE_NAME,
    REQUIRED_PREREQUISITE_NAME,
    MeasurementPropertyRatingResult,
    PrerequisiteDecision,
    PrerequisiteStatus,
    rate_criterion_validity,
    rate_cross_cultural_validity_measurement_invariance,
    rate_hypotheses_testing_for_construct_validity,
    rate_internal_consistency,
    rate_measurement_error,
    rate_reliability,
    rate_responsiveness,
    rate_structural_validity,
)
from cosmin_assistant.models import (
    CosminBoxRating,
    CosminItemRating,
    EvidenceCertaintyLevel,
    InstrumentType,
    MeasurementPropertyRating,
    ProfileType,
    PropertyActivationStatus,
    ReviewerDecisionStatus,
    UncertaintyStatus,
)
from cosmin_assistant.profiles import get_profile
from cosmin_assistant.synthesize import (
    StudySynthesisInput,
    SynthesisAggregateResult,
    synthesize_first_pass,
)
from cosmin_assistant.utils import sha256_file

MEASUREMENT_PROPERTY_INTERPRETABILITY = "interpretability"
_MEASUREMENT_PROPERTIES_IN_ORDER: tuple[str, ...] = (
    MEASUREMENT_PROPERTY_STRUCTURAL_VALIDITY,
    MEASUREMENT_PROPERTY_INTERNAL_CONSISTENCY,
    MEASUREMENT_PROPERTY_CROSS_CULTURAL_VALIDITY,
    MEASUREMENT_PROPERTY_RELIABILITY,
    MEASUREMENT_PROPERTY_MEASUREMENT_ERROR,
    MEASUREMENT_PROPERTY_CRITERION_VALIDITY,
    MEASUREMENT_PROPERTY_CONSTRUCT_VALIDITY,
    MEASUREMENT_PROPERTY_RESPONSIVENESS,
)
_SYNTHESIS_INCLUDED_STATUSES: tuple[PropertyActivationStatus, ...] = (
    PropertyActivationStatus.DIRECT_CURRENT_STUDY_EVIDENCE,
    PropertyActivationStatus.MEASUREMENT_ERROR_SUPPORT_ONLY,
    PropertyActivationStatus.INTERPRETABILITY_ONLY,
    PropertyActivationStatus.REVIEWER_REQUIRED,
)
_N_FOR_INSTRUMENT_LABEL_RE = re.compile(
    r"\b[nN]\s*=\s*(\d+)\s*(?:for|in)\s+([A-Za-z0-9][A-Za-z0-9\-\s]{1,120})"
)
_INSTRUMENT_LABEL_WITH_N_RE = re.compile(
    r"([A-Za-z0-9][A-Za-z0-9\-\s]{1,120})\s*\$?\(\s*[nN]\s*=\s*(\d+)\s*\)\$?"
)


@dataclass(frozen=True)
class ProvisionalAssessmentRun:
    """Structured in-memory artifacts for one provisional end-to-end run."""

    article_path: str
    source_article_hash: str
    generated_at_utc: str
    profile_type: ProfileType
    parsed_document: ParsedMarkdownDocument
    context_extraction: ArticleContextExtractionResult
    statistics_extraction: ArticleStatisticsExtractionResult
    property_activation_decisions: tuple[PropertyActivationDecision, ...]
    rob_assessments: tuple[BoxAssessmentBundle, ...]
    measurement_property_results: tuple[MeasurementPropertyRatingResult, ...]
    synthesis_results: tuple[SynthesisAggregateResult, ...]
    grade_results: tuple[ModifiedGradeResult, ...]


def run_provisional_assessment(
    *,
    article_path: str | Path,
    profile_type: ProfileType | str,
) -> ProvisionalAssessmentRun:
    """Execute the provisional deterministic assessment pipeline."""

    resolved_profile = ProfileType(profile_type)
    _ = get_profile(resolved_profile)
    if resolved_profile is not ProfileType.PROM:
        msg = "provisional CLI currently supports the PROM profile only"
        raise ValueError(msg)

    parsed = parse_markdown_file(article_path)
    context = extract_context_from_parsed_document(parsed)
    statistics = extract_statistics_from_parsed_document(parsed)
    fallback_evidence_id = _fallback_evidence_id(parsed)
    source_article_hash = sha256_file(parsed.file_path)
    generated_at_utc = datetime.now(UTC).isoformat()

    study_context = context.study_contexts[0]
    study_id = study_context.study_id
    instrument_sample_size_index = _build_instrument_sample_size_index(
        parsed_document=parsed,
        context=context,
    )

    assessment_contexts = _resolve_assessment_instrument_contexts(
        context=context,
        statistics=statistics,
    )

    rob_assessments: list[BoxAssessmentBundle] = []
    measurement_results: list[MeasurementPropertyRatingResult] = []
    activation_decisions: list[PropertyActivationDecision] = []
    measurement_result_keys: dict[str, tuple[str, str]] = {}
    result_sample_sizes: dict[str, int | None] = {}

    structural_by_instrument: dict[str, MeasurementPropertyRatingResult] = {}

    for instrument_context in assessment_contexts:
        instrument_id = instrument_context.instrument_id
        instrument_name = _first_string_value(instrument_context.instrument_name) or "unknown"
        normalized_instrument_name = _normalize_instrument_name(instrument_name)

        instrument_candidates = _select_rating_candidates(
            statistics.candidates,
            target_instrument_name=instrument_name,
        )

        decisions = tuple(
            _build_property_activation_decision(
                study_id=study_id,
                instrument_context=instrument_context,
                study_context=study_context,
                property_name=property_name,
                instrument_candidates=instrument_candidates,
                target_instrument_name=normalized_instrument_name,
                parsed_document=parsed,
            )
            for property_name in _MEASUREMENT_PROPERTIES_IN_ORDER
        )
        interpretability_decision = _build_interpretability_activation_decision(
            study_id=study_id,
            instrument_context=instrument_context,
            instrument_candidates=instrument_candidates,
        )
        if interpretability_decision is not None:
            decisions = (*decisions, interpretability_decision)
        activation_decisions.extend(decisions)

        for decision in decisions:
            property_candidates = _candidates_for_property(
                candidates=instrument_candidates,
                measurement_property=decision.measurement_property,
            )
            resolved_sample_size = _resolve_sample_size_for_result(
                study_context=study_context,
                instrument_context=instrument_context,
                measurement_property=decision.measurement_property,
                instrument_sample_size_index=instrument_sample_size_index,
            )

            if (
                decision.activation_status
                is not PropertyActivationStatus.DIRECT_CURRENT_STUDY_EVIDENCE
            ):
                non_direct_result = _build_non_direct_measurement_result(
                    study_id=study_id,
                    instrument_id=instrument_id,
                    decision=decision,
                    candidates=property_candidates,
                    sample_size=resolved_sample_size,
                )
                measurement_results.append(non_direct_result)
                measurement_result_keys[non_direct_result.id] = (
                    non_direct_result.instrument_id,
                    non_direct_result.measurement_property,
                )
                result_sample_sizes[non_direct_result.id] = resolved_sample_size
                continue

            box_bundle, rating_result = _execute_direct_property_pipeline(
                study_id=study_id,
                instrument_id=instrument_id,
                profile_type=resolved_profile,
                measurement_property=decision.measurement_property,
                candidates=property_candidates,
                fallback_evidence_id=fallback_evidence_id,
                sample_size=resolved_sample_size,
                study_context=study_context,
                structural_prerequisite_result=structural_by_instrument.get(instrument_id),
            )
            if box_bundle is not None:
                rob_assessments.append(box_bundle)

            updated_inputs = dict(rating_result.inputs_used)
            updated_inputs["sample_size_selected"] = resolved_sample_size
            rating_result = rating_result.model_copy(
                update={
                    "activation_status": decision.activation_status,
                    "inputs_used": updated_inputs,
                }
            )
            measurement_results.append(rating_result)
            measurement_result_keys[rating_result.id] = (
                rating_result.instrument_id,
                rating_result.measurement_property,
            )
            result_sample_sizes[rating_result.id] = resolved_sample_size

            if rating_result.measurement_property == MEASUREMENT_PROPERTY_STRUCTURAL_VALIDITY:
                structural_by_instrument[instrument_id] = rating_result

    instrument_lookup = {
        context_item.instrument_id: context_item for context_item in context.instrument_contexts
    }

    synthesis_inputs = tuple(
        StudySynthesisInput(
            id=result.id,
            study_id=result.study_id,
            instrument_name=_first_string_value(
                instrument_lookup[result.instrument_id].instrument_name
            )
            or "unknown",
            instrument_version=_first_string_value(
                instrument_lookup[result.instrument_id].instrument_version
            ),
            subscale=_first_string_value(instrument_lookup[result.instrument_id].subscale),
            measurement_property=result.measurement_property,
            rating=result.computed_rating,
            sample_size=result_sample_sizes.get(result.id),
            evidence_span_ids=result.evidence_span_ids or (fallback_evidence_id,),
            study_explanation=result.explanation,
            activation_status=result.activation_status,
        )
        for result in measurement_results
        if result.activation_status in _SYNTHESIS_INCLUDED_STATUSES
    )
    synthesis_inputs = _normalize_synthesis_inputs_by_instrument_family(synthesis_inputs)
    synthesis_results = synthesize_first_pass(synthesis_inputs)

    rob_by_key = {
        (bundle.box_assessment.instrument_id, bundle.box_assessment.measurement_property): bundle
        for bundle in rob_assessments
    }

    grade_results: list[ModifiedGradeResult] = []
    for synthesis_result in synthesis_results:
        if (
            synthesis_result.activation_status
            is not PropertyActivationStatus.DIRECT_CURRENT_STUDY_EVIDENCE
        ):
            grade_results.append(
                _grade_skipped_result(
                    synthesis_result=synthesis_result,
                    reason=(
                        "Modified GRADE was not executed because this synthesized result was "
                        f"classified as {synthesis_result.activation_status.value}."
                    ),
                )
            )
            continue

        candidate_bundles = [
            rob_by_key[key]
            for key in (
                measurement_result_keys.get(entry.id) for entry in synthesis_result.study_entries
            )
            if key is not None and key in rob_by_key
        ]
        box_bundle = _select_most_conservative_box_bundle(tuple(candidate_bundles))

        grade_results.append(
            apply_modified_grade(
                synthesis_result=synthesis_result,
                risk_of_bias=_risk_of_bias_input(
                    box_bundle=box_bundle,
                    fallback_evidence_id=fallback_evidence_id,
                ),
                indirectness=DomainDowngradeInput(
                    domain=ModifiedGradeDomain.INDIRECTNESS,
                    severity=DowngradeSeverity.NONE,
                    reason=None,
                    evidence_span_ids=(),
                    explanation=None,
                ),
            )
        )

    return ProvisionalAssessmentRun(
        article_path=str(Path(article_path).resolve()),
        source_article_hash=source_article_hash,
        generated_at_utc=generated_at_utc,
        profile_type=resolved_profile,
        parsed_document=parsed,
        context_extraction=context,
        statistics_extraction=statistics,
        property_activation_decisions=tuple(activation_decisions),
        rob_assessments=tuple(rob_assessments),
        measurement_property_results=tuple(measurement_results),
        synthesis_results=synthesis_results,
        grade_results=tuple(grade_results),
    )


def _resolve_assessment_instrument_contexts(
    *,
    context: ArticleContextExtractionResult,
    statistics: ArticleStatisticsExtractionResult,
) -> tuple[InstrumentContextExtractionResult, ...]:
    if not context.instrument_contexts:
        return ()
    study_intent = (
        context.study_contexts[0].study_intent if context.study_contexts else StudyIntent.MIXED
    )

    direct_candidate_hints = {
        _normalize_instrument_name(hint)
        for candidate in statistics.candidates
        if candidate.evidence_source is EvidenceSourceType.CURRENT_STUDY
        and candidate.supports_direct_assessment
        for hint in candidate.instrument_name_hints
    }

    selected: list[InstrumentContextExtractionResult] = []
    for instrument_context in context.instrument_contexts:
        if instrument_context.instrument_role in (
            InstrumentContextRole.COMPARATOR,
            InstrumentContextRole.COMPARATOR_ONLY,
            InstrumentContextRole.BACKGROUND_ONLY,
        ):
            continue
        instrument_name = _first_string_value(instrument_context.instrument_name)
        normalized = _normalize_instrument_name(instrument_name or "") if instrument_name else ""
        has_direct_signal = bool(normalized) and _hint_set_matches_target(
            target_name=normalized,
            hint_names=direct_candidate_hints,
        )
        non_comparator_direct = _has_non_comparator_direct_signal(
            normalized_instrument_name=normalized,
            statistics=statistics,
        )

        if instrument_context.instrument_role in (
            InstrumentContextRole.TARGET_UNDER_APPRAISAL,
            InstrumentContextRole.CO_PRIMARY_OUTCOME_INSTRUMENT,
            InstrumentContextRole.SECONDARY_OUTCOME_INSTRUMENT,
        ):
            selected.append(instrument_context)
            continue

        if (
            study_intent is StudyIntent.PSYCHOMETRIC_VALIDATION
            and context.target_instrument_id is not None
        ):
            # In validation studies keep appraisal scoped to target-under-appraisal
            # contexts unless the comparator was explicitly elevated above.
            continue

        if has_direct_signal and non_comparator_direct:
            selected.append(instrument_context)
            continue

        if (
            instrument_context.instrument_role is InstrumentContextRole.ADDITIONAL
            and context.target_instrument_id is None
        ):
            # Keep additional contexts only when no explicit target exists.
            selected.append(instrument_context)

    if not selected:
        return (context.instrument_contexts[0],)
    return tuple(selected)


def _has_non_comparator_direct_signal(
    *,
    normalized_instrument_name: str,
    statistics: ArticleStatisticsExtractionResult,
) -> bool:
    if not normalized_instrument_name:
        return False

    for candidate in statistics.candidates:
        if candidate.evidence_source is not EvidenceSourceType.CURRENT_STUDY:
            continue
        if not candidate.supports_direct_assessment:
            continue

        candidate_hints = {
            _normalize_instrument_name(hint) for hint in candidate.instrument_name_hints
        }
        if not _hint_set_matches_target(
            target_name=normalized_instrument_name,
            hint_names=candidate_hints,
        ):
            continue

        comparator_hints = {
            _normalize_instrument_name(hint) for hint in candidate.comparator_instrument_hints
        }
        # Comparator-linked candidates should not be treated as direct
        # assessment evidence for the comparator instrument itself.
        if _hint_set_matches_target(
            target_name=normalized_instrument_name,
            hint_names=comparator_hints,
        ):
            continue
        return True

    return False


def _build_property_activation_decision(
    *,
    study_id: str,
    instrument_context: InstrumentContextExtractionResult,
    study_context: StudyContextExtractionResult,
    property_name: str,
    instrument_candidates: tuple[StatisticCandidate, ...],
    target_instrument_name: str,
    parsed_document: ParsedMarkdownDocument,
) -> PropertyActivationDecision:
    property_candidates = _candidates_for_property(
        candidates=instrument_candidates,
        measurement_property=property_name,
    )

    direct_candidates = tuple(
        candidate
        for candidate in property_candidates
        if candidate.evidence_source is EvidenceSourceType.CURRENT_STUDY
        and candidate.supports_direct_assessment
        and not _is_excluded_for_target(candidate, target_instrument_name)
    )
    background_candidates = tuple(
        candidate
        for candidate in property_candidates
        if candidate.evidence_source is EvidenceSourceType.BACKGROUND_CITATION
    )
    interpretability_candidates = tuple(
        candidate
        for candidate in property_candidates
        if candidate.evidence_source is EvidenceSourceType.INTERPRETABILITY_ONLY
    )
    comparator_candidates = tuple(
        candidate for candidate in property_candidates if candidate.comparator_instrument_hints
    )

    not_assessed_properties = _properties_not_assessed(study_context)
    if property_name in not_assessed_properties and not direct_candidates:
        evidence_ids = _field_evidence_span_ids(study_context.measurement_properties_not_assessed)
        return PropertyActivationDecision(
            id=stable_activation_id(
                "activate",
                study_id,
                instrument_context.instrument_id,
                property_name,
                PropertyActivationStatus.NOT_ASSESSED_IN_CURRENT_STUDY.value,
            ),
            study_id=study_id,
            instrument_id=instrument_context.instrument_id,
            instrument_name=_first_string_value(instrument_context.instrument_name) or "unknown",
            instrument_type=instrument_context.instrument_type,
            measurement_property=property_name,
            activation_status=PropertyActivationStatus.NOT_ASSESSED_IN_CURRENT_STUDY,
            explanation=(
                "Property was explicitly described as not assessed in the current study text."
            ),
            evidence_span_ids=evidence_ids,
            rating_input_source_flags=("not_assessed_in_current_study",),
        )

    if (
        property_name in STEP6_PROM_ITEM_BASED_PROPERTIES
        and instrument_context.instrument_type
        in (InstrumentType.PERFORMANCE_TEST, InstrumentType.PBOM)
    ):
        evidence_ids = instrument_context.instrument_type_evidence_span_ids
        return PropertyActivationDecision(
            id=stable_activation_id(
                "activate",
                study_id,
                instrument_context.instrument_id,
                property_name,
                PropertyActivationStatus.NOT_APPLICABLE_FOR_INSTRUMENT_TYPE.value,
            ),
            study_id=study_id,
            instrument_id=instrument_context.instrument_id,
            instrument_name=_first_string_value(instrument_context.instrument_name) or "unknown",
            instrument_type=instrument_context.instrument_type,
            measurement_property=property_name,
            activation_status=PropertyActivationStatus.NOT_APPLICABLE_FOR_INSTRUMENT_TYPE,
            explanation=(
                "Item-based Step-6 property is not applicable for this instrument type based on "
                "detected test/tool characteristics."
            ),
            evidence_span_ids=evidence_ids,
            rating_input_source_flags=("instrument_type_gate",),
        )

    if property_name == MEASUREMENT_PROPERTY_RELIABILITY and direct_candidates:
        has_reliability_stat = any(
            candidate.statistic_type
            in (
                StatisticType.ICC,
                StatisticType.KAPPA,
                StatisticType.WEIGHTED_KAPPA,
            )
            for candidate in direct_candidates
        )
        if has_reliability_stat:
            return _activation_from_candidates(
                study_id=study_id,
                instrument_context=instrument_context,
                property_name=property_name,
                status=PropertyActivationStatus.DIRECT_CURRENT_STUDY_EVIDENCE,
                candidates=direct_candidates,
                explanation=(
                    "Direct current-study reliability statistics were explicitly reported "
                    "(ICC/kappa)."
                ),
            )

    if property_name == MEASUREMENT_PROPERTY_MEASUREMENT_ERROR and direct_candidates:
        has_numeric_mic = any(
            candidate.statistic_type is StatisticType.MIC
            and isinstance(candidate.value_normalized, float)
            for candidate in direct_candidates
        )
        has_support_only = any(
            candidate.statistic_type
            in (
                StatisticType.SEM,
                StatisticType.SDC,
                StatisticType.LOA,
            )
            or (
                candidate.statistic_type is StatisticType.MIC
                and not isinstance(candidate.value_normalized, float)
            )
            for candidate in direct_candidates
        )
        if has_support_only and not has_numeric_mic:
            return _activation_from_candidates(
                study_id=study_id,
                instrument_context=instrument_context,
                property_name=property_name,
                status=PropertyActivationStatus.MEASUREMENT_ERROR_SUPPORT_ONLY,
                candidates=direct_candidates,
                explanation=(
                    "Measurement-error support evidence (SEM/SDC/LoA/MIC mention) was found "
                    "without required comparison inputs for direct sufficiency appraisal."
                ),
            )

    if property_name == MEASUREMENT_PROPERTY_CRITERION_VALIDITY and direct_candidates:
        if _has_explicit_gold_standard_evidence(direct_candidates):
            return _activation_from_candidates(
                study_id=study_id,
                instrument_context=instrument_context,
                property_name=property_name,
                status=PropertyActivationStatus.DIRECT_CURRENT_STUDY_EVIDENCE,
                candidates=direct_candidates,
                explanation=(
                    "Direct current-study criterion-validity evidence with explicit "
                    "gold-standard rationale."
                ),
            )
        if _article_reports_no_gold_standard(parsed_document):
            return _activation_from_candidates(
                study_id=study_id,
                instrument_context=instrument_context,
                property_name=property_name,
                status=PropertyActivationStatus.NOT_ASSESSED_IN_CURRENT_STUDY,
                candidates=direct_candidates,
                explanation=(
                    "Criterion validity was not activated because the article explicitly "
                    "reported the absence of a gold standard; comparator-based associations "
                    "are routed under hypotheses testing for construct validity."
                ),
            )
        return _activation_from_candidates(
            study_id=study_id,
            instrument_context=instrument_context,
            property_name=property_name,
            status=PropertyActivationStatus.NOT_ASSESSED_IN_CURRENT_STUDY,
            candidates=direct_candidates,
            explanation=(
                "Criterion validity was not activated because no explicit gold-standard "
                "justification was reported; comparator-based associations are routed under "
                "hypotheses testing for construct validity."
            ),
        )

    if property_name == MEASUREMENT_PROPERTY_RESPONSIVENESS and direct_candidates:
        has_change_analysis = any(
            _is_change_analysis_candidate(candidate) for candidate in direct_candidates
        )
        if has_change_analysis:
            return _activation_from_candidates(
                study_id=study_id,
                instrument_context=instrument_context,
                property_name=property_name,
                status=PropertyActivationStatus.DIRECT_CURRENT_STUDY_EVIDENCE,
                candidates=direct_candidates,
                explanation=(
                    "Direct longitudinal change analysis for the instrument was detected."
                ),
            )
        return _activation_from_candidates(
            study_id=study_id,
            instrument_context=instrument_context,
            property_name=property_name,
            status=PropertyActivationStatus.REVIEWER_REQUIRED,
            candidates=direct_candidates,
            explanation=(
                "Repeated measurements were detected without clear direct responsiveness "
                "change-analysis evidence."
            ),
        )

    if direct_candidates:
        return _activation_from_candidates(
            study_id=study_id,
            instrument_context=instrument_context,
            property_name=property_name,
            status=PropertyActivationStatus.DIRECT_CURRENT_STUDY_EVIDENCE,
            candidates=direct_candidates,
            explanation="Direct current-study evidence was available for this property.",
        )

    if comparator_candidates:
        return _activation_from_candidates(
            study_id=study_id,
            instrument_context=instrument_context,
            property_name=property_name,
            status=PropertyActivationStatus.COMPARATOR_BASED_EVIDENCE,
            candidates=comparator_candidates,
            explanation=(
                "Evidence was attached to comparator-instrument context rather than direct "
                "appraisal."
            ),
        )

    if interpretability_candidates:
        return _activation_from_candidates(
            study_id=study_id,
            instrument_context=instrument_context,
            property_name=property_name,
            status=PropertyActivationStatus.INTERPRETABILITY_ONLY,
            candidates=interpretability_candidates,
            explanation=(
                "Evidence was interpretability-oriented and not direct psychometric appraisal."
            ),
        )

    if background_candidates:
        return _activation_from_candidates(
            study_id=study_id,
            instrument_context=instrument_context,
            property_name=property_name,
            status=PropertyActivationStatus.INDIRECT_ONLY,
            candidates=background_candidates,
            explanation=(
                "Only background/cited evidence was found; no direct current-study evidence."
            ),
        )

    return PropertyActivationDecision(
        id=stable_activation_id(
            "activate",
            study_id,
            instrument_context.instrument_id,
            property_name,
            PropertyActivationStatus.NOT_ASSESSED_IN_CURRENT_STUDY.value,
        ),
        study_id=study_id,
        instrument_id=instrument_context.instrument_id,
        instrument_name=_first_string_value(instrument_context.instrument_name) or "unknown",
        instrument_type=instrument_context.instrument_type,
        measurement_property=property_name,
        activation_status=PropertyActivationStatus.NOT_ASSESSED_IN_CURRENT_STUDY,
        explanation=(
            "No direct current-study evidence for this property was detected in the "
            "current article context."
        ),
        evidence_span_ids=_field_evidence_span_ids(study_context.measurement_properties_mentioned),
        rating_input_source_flags=("no_direct_property_evidence_detected",),
    )


def _build_interpretability_activation_decision(
    *,
    study_id: str,
    instrument_context: InstrumentContextExtractionResult,
    instrument_candidates: tuple[StatisticCandidate, ...],
) -> PropertyActivationDecision | None:
    interpretability_candidates = _candidates_for_property(
        candidates=instrument_candidates,
        measurement_property=MEASUREMENT_PROPERTY_INTERPRETABILITY,
    )
    if not interpretability_candidates:
        return None

    anchor_numeric_mic = tuple(
        candidate
        for candidate in interpretability_candidates
        if candidate.statistic_type is StatisticType.MIC
        and isinstance(candidate.value_normalized, float)
        and candidate.evidence_source
        in (EvidenceSourceType.CURRENT_STUDY, EvidenceSourceType.INTERPRETABILITY_ONLY)
        and EvidenceMethodLabel.ANCHOR_BASED in candidate.method_labels
    )
    if not anchor_numeric_mic:
        return None

    return _activation_from_candidates(
        study_id=study_id,
        instrument_context=instrument_context,
        property_name=MEASUREMENT_PROPERTY_INTERPRETABILITY,
        status=PropertyActivationStatus.INTERPRETABILITY_ONLY,
        candidates=anchor_numeric_mic,
        explanation=(
            "Anchor-based MIC/MCID evidence from the current study was routed to "
            "interpretability-only output."
        ),
    )


def _activation_from_candidates(
    *,
    study_id: str,
    instrument_context: InstrumentContextExtractionResult,
    property_name: str,
    status: PropertyActivationStatus,
    candidates: tuple[StatisticCandidate, ...],
    explanation: str,
) -> PropertyActivationDecision:
    return PropertyActivationDecision(
        id=stable_activation_id(
            "activate",
            study_id,
            instrument_context.instrument_id,
            property_name,
            status.value,
            ",".join(candidate.id for candidate in candidates),
        ),
        study_id=study_id,
        instrument_id=instrument_context.instrument_id,
        instrument_name=_first_string_value(instrument_context.instrument_name) or "unknown",
        instrument_type=instrument_context.instrument_type,
        measurement_property=property_name,
        activation_status=status,
        explanation=explanation,
        evidence_span_ids=merged_candidate_evidence(candidates),
        rating_input_source_flags=candidate_source_flags(candidates),
    )


def _execute_direct_property_pipeline(
    *,
    study_id: str,
    instrument_id: str,
    profile_type: ProfileType,
    measurement_property: str,
    candidates: tuple[StatisticCandidate, ...],
    fallback_evidence_id: str,
    sample_size: int | None,
    study_context: StudyContextExtractionResult,
    structural_prerequisite_result: MeasurementPropertyRatingResult | None,
) -> tuple[BoxAssessmentBundle | None, MeasurementPropertyRatingResult]:
    if measurement_property == MEASUREMENT_PROPERTY_STRUCTURAL_VALIDITY:
        box_bundle = assess_box3_structural_validity(
            study_id=study_id,
            instrument_id=instrument_id,
            item_inputs=_box3_inputs(
                statistic_candidates=candidates,
                sample_size=sample_size,
                fallback_evidence_id=fallback_evidence_id,
            ),
        )
        rating = rate_structural_validity(
            study_id=study_id,
            instrument_id=instrument_id,
            statistic_candidates=candidates,
        )
        return box_bundle, rating

    if measurement_property == MEASUREMENT_PROPERTY_INTERNAL_CONSISTENCY:
        box_bundle = assess_box4_internal_consistency(
            study_id=study_id,
            instrument_id=instrument_id,
            item_inputs=_box4_inputs(
                statistic_candidates=candidates,
                fallback_evidence_id=fallback_evidence_id,
            ),
        )
        prerequisite = _structural_validity_prerequisite(structural_prerequisite_result)
        rating = rate_internal_consistency(
            study_id=study_id,
            instrument_id=instrument_id,
            statistic_candidates=candidates,
            prerequisite_decisions=(prerequisite,),
        )
        return box_bundle, rating

    if measurement_property == MEASUREMENT_PROPERTY_CROSS_CULTURAL_VALIDITY:
        box_bundle = assess_box5_cross_cultural_validity_measurement_invariance(
            study_id=study_id,
            instrument_id=instrument_id,
            item_inputs=_box5_inputs(
                statistic_candidates=candidates,
                fallback_evidence_id=fallback_evidence_id,
            ),
        )
        rating = rate_cross_cultural_validity_measurement_invariance(
            study_id=study_id,
            instrument_id=instrument_id,
            statistic_candidates=candidates,
            profile_type=profile_type,
        )
        return box_bundle, rating

    if measurement_property == MEASUREMENT_PROPERTY_RELIABILITY:
        box_bundle = assess_box6_reliability(
            study_id=study_id,
            instrument_id=instrument_id,
            item_inputs=_box6_inputs(
                statistic_candidates=candidates,
                fallback_evidence_id=fallback_evidence_id,
                follow_up_interval=study_context.follow_up_interval,
            ),
        )
        rating = rate_reliability(
            study_id=study_id,
            instrument_id=instrument_id,
            statistic_candidates=candidates,
        )
        return box_bundle, rating

    if measurement_property == MEASUREMENT_PROPERTY_MEASUREMENT_ERROR:
        box_bundle = assess_box7_measurement_error(
            study_id=study_id,
            instrument_id=instrument_id,
            item_inputs=_box7_inputs(
                statistic_candidates=candidates,
                fallback_evidence_id=fallback_evidence_id,
            ),
        )
        rating = rate_measurement_error(
            study_id=study_id,
            instrument_id=instrument_id,
            statistic_candidates=candidates,
            profile_type=profile_type,
        )
        return box_bundle, rating

    if measurement_property == MEASUREMENT_PROPERTY_CRITERION_VALIDITY:
        box_bundle = assess_box8_criterion_validity(
            study_id=study_id,
            instrument_id=instrument_id,
            item_inputs=_box8_inputs(
                statistic_candidates=candidates,
                fallback_evidence_id=fallback_evidence_id,
            ),
        )
        prerequisite = _gold_standard_prerequisite(candidates)
        rating = rate_criterion_validity(
            study_id=study_id,
            instrument_id=instrument_id,
            statistic_candidates=candidates,
            prerequisite_decisions=(prerequisite,),
            profile_type=profile_type,
        )
        return box_bundle, rating

    if measurement_property == MEASUREMENT_PROPERTY_CONSTRUCT_VALIDITY:
        box_bundle = assess_box9_hypotheses_testing_for_construct_validity(
            study_id=study_id,
            instrument_id=instrument_id,
            item_inputs=_box9_inputs(
                statistic_candidates=candidates,
                fallback_evidence_id=fallback_evidence_id,
            ),
        )
        prerequisite = _hypotheses_prerequisite(candidates)
        rating = rate_hypotheses_testing_for_construct_validity(
            study_id=study_id,
            instrument_id=instrument_id,
            statistic_candidates=candidates,
            prerequisite_decisions=(prerequisite,),
            profile_type=profile_type,
        )
        return box_bundle, rating

    if measurement_property == MEASUREMENT_PROPERTY_RESPONSIVENESS:
        box_bundle = assess_box10_responsiveness(
            study_id=study_id,
            instrument_id=instrument_id,
            item_inputs=_box10_inputs(
                statistic_candidates=candidates,
                fallback_evidence_id=fallback_evidence_id,
            ),
        )
        prerequisite = _hypotheses_prerequisite(candidates)
        rating = rate_responsiveness(
            study_id=study_id,
            instrument_id=instrument_id,
            statistic_candidates=candidates,
            prerequisite_decisions=(prerequisite,),
            profile_type=profile_type,
        )
        return box_bundle, rating

    raise ValueError(f"unsupported direct pipeline property: {measurement_property}")


def _build_non_direct_measurement_result(
    *,
    study_id: str,
    instrument_id: str,
    decision: PropertyActivationDecision,
    candidates: tuple[StatisticCandidate, ...],
    sample_size: int | None,
) -> MeasurementPropertyRatingResult:
    uncertainty_status, reviewer_status = _activation_uncertainty(decision.activation_status)
    evidence_span_ids = decision.evidence_span_ids or merged_candidate_evidence(candidates)

    return MeasurementPropertyRatingResult(
        id=_stable_id(
            "mpr",
            study_id,
            instrument_id,
            decision.measurement_property,
            decision.activation_status.value,
            ",".join(evidence_span_ids),
        ),
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=decision.measurement_property,
        rule_name="ELIGIBILITY_GATE_V1",
        raw_results=(),
        computed_rating=MeasurementPropertyRating.INDETERMINATE,
        explanation=decision.explanation,
        inputs_used={
            "activation_status": decision.activation_status.value,
            "rating_input_source_flags": list(decision.rating_input_source_flags),
            "sample_size_selected": sample_size,
        },
        evidence_span_ids=evidence_span_ids,
        activation_status=decision.activation_status,
        uncertainty_status=uncertainty_status,
        reviewer_decision_status=reviewer_status,
    )


def _activation_uncertainty(
    status: PropertyActivationStatus,
) -> tuple[UncertaintyStatus, ReviewerDecisionStatus]:
    if status is PropertyActivationStatus.NOT_APPLICABLE_FOR_INSTRUMENT_TYPE:
        return (UncertaintyStatus.CERTAIN, ReviewerDecisionStatus.NOT_REQUIRED)
    if status in (
        PropertyActivationStatus.NOT_ASSESSED_IN_CURRENT_STUDY,
        PropertyActivationStatus.INDIRECT_ONLY,
        PropertyActivationStatus.INTERPRETABILITY_ONLY,
        PropertyActivationStatus.MEASUREMENT_ERROR_SUPPORT_ONLY,
    ):
        return (UncertaintyStatus.MISSING_EVIDENCE, ReviewerDecisionStatus.PENDING)
    if status is PropertyActivationStatus.COMPARATOR_BASED_EVIDENCE:
        return (UncertaintyStatus.AMBIGUOUS, ReviewerDecisionStatus.PENDING)
    return (UncertaintyStatus.REVIEWER_REQUIRED, ReviewerDecisionStatus.PENDING)


def _candidates_for_property(
    *,
    candidates: tuple[StatisticCandidate, ...],
    measurement_property: str,
) -> tuple[StatisticCandidate, ...]:
    route_by_property: dict[str, tuple[MeasurementPropertyRoute, ...]] = {
        MEASUREMENT_PROPERTY_STRUCTURAL_VALIDITY: (MeasurementPropertyRoute.STRUCTURAL_VALIDITY,),
        MEASUREMENT_PROPERTY_INTERNAL_CONSISTENCY: (MeasurementPropertyRoute.INTERNAL_CONSISTENCY,),
        MEASUREMENT_PROPERTY_CROSS_CULTURAL_VALIDITY: (
            MeasurementPropertyRoute.HYPOTHESES_TESTING_FOR_CONSTRUCT_VALIDITY,
        ),
        MEASUREMENT_PROPERTY_RELIABILITY: (MeasurementPropertyRoute.RELIABILITY,),
        MEASUREMENT_PROPERTY_MEASUREMENT_ERROR: (
            MeasurementPropertyRoute.MEASUREMENT_ERROR_SUPPORT,
        ),
        MEASUREMENT_PROPERTY_CRITERION_VALIDITY: (
            MeasurementPropertyRoute.HYPOTHESES_TESTING_FOR_CONSTRUCT_VALIDITY,
        ),
        MEASUREMENT_PROPERTY_CONSTRUCT_VALIDITY: (
            MeasurementPropertyRoute.HYPOTHESES_TESTING_FOR_CONSTRUCT_VALIDITY,
        ),
        MEASUREMENT_PROPERTY_RESPONSIVENESS: (MeasurementPropertyRoute.RESPONSIVENESS,),
        MEASUREMENT_PROPERTY_INTERPRETABILITY: (MeasurementPropertyRoute.INTERPRETABILITY,),
    }

    routes = route_by_property.get(measurement_property, ())

    filtered = tuple(
        candidate
        for candidate in candidates
        if any(route in routes for route in candidate.measurement_property_routes)
    )

    if measurement_property == MEASUREMENT_PROPERTY_CROSS_CULTURAL_VALIDITY:
        return tuple(
            candidate
            for candidate in filtered
            if candidate.statistic_type is StatisticType.MEASUREMENT_INVARIANCE_FINDING
        )

    if measurement_property == MEASUREMENT_PROPERTY_CRITERION_VALIDITY:
        return tuple(
            candidate
            for candidate in filtered
            if candidate.statistic_type in (StatisticType.CORRELATION, StatisticType.AUC)
        )

    return filtered


def _properties_not_assessed(study_context: StudyContextExtractionResult) -> set[str]:
    field = study_context.measurement_properties_not_assessed
    if field is None or field.status is FieldDetectionStatus.NOT_DETECTED:
        return set()

    values: set[str] = set()
    for candidate in field.candidates:
        normalized = candidate.normalized_value
        if isinstance(normalized, tuple):
            values.update(value for value in normalized if isinstance(value, str))
        elif isinstance(normalized, str):
            values.add(normalized)
    return values


def _field_evidence_span_ids(field: ContextFieldExtraction | None) -> tuple[str, ...]:
    if field is None:
        return ()
    return tuple(
        sorted(
            {span_id for candidate in field.candidates for span_id in candidate.evidence_span_ids}
        )
    )


def _has_explicit_gold_standard_evidence(
    candidates: tuple[StatisticCandidate, ...],
) -> bool:
    negative_signals = (
        "lack of a gold standard",
        "no gold standard",
        "without a gold standard",
        "without gold standard",
        "not available as a gold standard",
        "could not be established",
        "could not be verified",
    )
    for candidate in candidates:
        text_lower = candidate.surrounding_text.lower()
        if "gold standard" not in text_lower:
            continue
        if any(signal in text_lower for signal in negative_signals):
            continue
        if "not a gold standard" in text_lower:
            continue
        if "not the gold standard" in text_lower:
            continue
        if "no accepted gold standard" in text_lower:
            continue
        if "gold standard" in text_lower:
            return True
    return False


def _article_reports_no_gold_standard(parsed_document: ParsedMarkdownDocument) -> bool:
    negative_patterns = (
        "no gold standard",
        "no gold standards",
        "lack of a gold standard",
        "lack of gold standard",
        "without a gold standard",
        "without gold standard",
        "no accepted gold standard",
    )
    for sentence in parsed_document.sentences:
        text_lower = sentence.provenance.raw_text.lower()
        heading_lower = " ".join(sentence.heading_path).lower()
        if "references" in heading_lower:
            continue
        if "gold standard" not in text_lower:
            continue
        if any(pattern in text_lower for pattern in negative_patterns):
            return True
    return False


def _gold_standard_prerequisite(
    candidates: tuple[StatisticCandidate, ...],
) -> PrerequisiteDecision:
    evidence_span_ids = merged_candidate_evidence(candidates)
    if _has_explicit_gold_standard_evidence(candidates):
        return PrerequisiteDecision(
            name=REQUIRED_GOLD_STANDARD_PREREQUISITE_NAME,
            status=PrerequisiteStatus.MET,
            detail="Gold-standard suitability was explicitly justified in study text.",
            evidence_span_ids=evidence_span_ids,
        )
    return PrerequisiteDecision(
        name=REQUIRED_GOLD_STANDARD_PREREQUISITE_NAME,
        status=PrerequisiteStatus.MISSING,
        detail="Gold-standard suitability was not explicit in direct current-study evidence.",
        evidence_span_ids=evidence_span_ids,
    )


def _hypotheses_prerequisite(
    candidates: tuple[StatisticCandidate, ...],
) -> PrerequisiteDecision:
    evidence_span_ids = merged_candidate_evidence(candidates)
    if any(
        candidate.responsiveness_hypothesis_status is ResponsivenessHypothesisStatus.PREDEFINED
        for candidate in candidates
    ):
        return PrerequisiteDecision(
            name=REQUIRED_HYPOTHESES_PREREQUISITE_NAME,
            status=PrerequisiteStatus.MET,
            detail="Predefined hypotheses were explicitly reported.",
            evidence_span_ids=evidence_span_ids,
        )

    if any("a priori" in candidate.surrounding_text.lower() for candidate in candidates):
        return PrerequisiteDecision(
            name=REQUIRED_HYPOTHESES_PREREQUISITE_NAME,
            status=PrerequisiteStatus.MET,
            detail="A-priori hypotheses language was detected.",
            evidence_span_ids=evidence_span_ids,
        )

    return PrerequisiteDecision(
        name=REQUIRED_HYPOTHESES_PREREQUISITE_NAME,
        status=PrerequisiteStatus.MISSING,
        detail="Predefined hypotheses were not explicit in direct evidence.",
        evidence_span_ids=evidence_span_ids,
    )


def _is_change_analysis_candidate(candidate: StatisticCandidate) -> bool:
    text_lower = candidate.surrounding_text.lower()
    if any(
        token in text_lower
        for token in (
            "mcid",
            "mic",
            "mid",
            "minimum clinically important difference",
            "minimal clinically important difference",
        )
    ) and not any(
        token in text_lower
        for token in (
            "responsiveness",
            "effect size",
            "standardized response mean",
            "srm",
        )
    ):
        return False
    if candidate.value_normalized == "longitudinal_change_reported":
        return True
    return any(token in text_lower for token in ("change", "baseline", "follow-up", "difference"))


def _resolve_target_instrument_context(
    context: ArticleContextExtractionResult,
) -> InstrumentContextExtractionResult:
    if context.target_instrument_id:
        for instrument_context in context.instrument_contexts:
            if instrument_context.instrument_id == context.target_instrument_id:
                return instrument_context

    for instrument_context in context.instrument_contexts:
        if instrument_context.instrument_role in (
            InstrumentContextRole.TARGET_UNDER_APPRAISAL,
            InstrumentContextRole.CO_PRIMARY_OUTCOME_INSTRUMENT,
        ):
            return instrument_context

    return context.instrument_contexts[0]


def _resolve_sample_size_for_property(
    *,
    study_context: StudyContextExtractionResult,
    measurement_property: str,
) -> int | None:
    prioritized_by_property: dict[str, tuple[SampleSizeRole, ...]] = {
        MEASUREMENT_PROPERTY_RELIABILITY: (
            SampleSizeRole.RETEST,
            SampleSizeRole.VALIDATION,
            SampleSizeRole.ANALYZED,
            SampleSizeRole.ENROLLMENT,
            SampleSizeRole.OTHER,
        ),
        MEASUREMENT_PROPERTY_CONSTRUCT_VALIDITY: (
            SampleSizeRole.VALIDATION,
            SampleSizeRole.ANALYZED,
            SampleSizeRole.ENROLLMENT,
            SampleSizeRole.RETEST,
            SampleSizeRole.OTHER,
        ),
    }
    default_order = (
        SampleSizeRole.VALIDATION,
        SampleSizeRole.RETEST,
        SampleSizeRole.ANALYZED,
        SampleSizeRole.ENROLLMENT,
        SampleSizeRole.OTHER,
    )
    order = prioritized_by_property.get(measurement_property, default_order)

    by_role: dict[SampleSizeRole, list[int]] = {}
    for observation in study_context.sample_size_observations:
        values = by_role.setdefault(observation.role, [])
        values.append(observation.sample_size_normalized)

    for role in order:
        values = by_role.get(role, [])
        if values:
            return values[0]

    for field in (
        study_context.validation_sample_n,
        study_context.retest_sample_n,
        study_context.sample_sizes,
    ):
        if field is None:
            continue
        value = _first_int_value(field)
        if value is not None:
            return value
    return None


def _resolve_sample_size_for_result(
    *,
    study_context: StudyContextExtractionResult,
    instrument_context: InstrumentContextExtractionResult,
    measurement_property: str,
    instrument_sample_size_index: dict[str, tuple[int, ...]],
) -> int | None:
    instrument_name = _first_string_value(instrument_context.instrument_name)
    if instrument_name:
        normalized_name = _normalize_instrument_name(instrument_name)
        values = instrument_sample_size_index.get(normalized_name, ())
        if values:
            return _select_representative_sample_size(values)

    return _resolve_sample_size_for_property(
        study_context=study_context,
        measurement_property=measurement_property,
    )


def _build_instrument_sample_size_index(
    *,
    parsed_document: ParsedMarkdownDocument,
    context: ArticleContextExtractionResult,
) -> dict[str, tuple[int, ...]]:
    known_instruments = {
        _normalize_instrument_name(name)
        for item in context.instrument_contexts
        for name in (_first_string_value(item.instrument_name),)
        if name
    }
    if not known_instruments:
        return {}

    by_instrument: dict[str, list[int]] = {name: [] for name in known_instruments}
    for sentence in parsed_document.sentences:
        text = sentence.provenance.raw_text
        by_instrument_for_sentence = _extract_instrument_sample_sizes_from_sentence(text=text)
        for normalized_name, value in by_instrument_for_sentence:
            if normalized_name in known_instruments:
                by_instrument[normalized_name].append(value)

    return {name: tuple(values) for name, values in by_instrument.items() if values}


def _extract_instrument_sample_sizes_from_sentence(*, text: str) -> tuple[tuple[str, int], ...]:
    extracted: list[tuple[str, int]] = []

    for match in _N_FOR_INSTRUMENT_LABEL_RE.finditer(text):
        value = int(match.group(1))
        label = match.group(2).strip()
        for candidate_label in _split_instrument_label_candidates(label):
            normalized_name = _normalize_instrument_name(candidate_label)
            extracted.append((normalized_name, value))

    for match in _INSTRUMENT_LABEL_WITH_N_RE.finditer(text):
        label = match.group(1).strip()
        value = int(match.group(2))
        for candidate_label in _split_instrument_label_candidates(label):
            normalized_name = _normalize_instrument_name(candidate_label)
            extracted.append((normalized_name, value))

    return tuple(dict.fromkeys(extracted))


def _split_instrument_label_candidates(raw_label: str) -> tuple[str, ...]:
    normalized = raw_label.replace(" and ", ",")
    parts = [item.strip(" :;,.()") for item in normalized.split(",")]
    candidates = tuple(item for item in parts if item)
    return candidates or (raw_label.strip(),)


def _select_representative_sample_size(values: tuple[int, ...]) -> int:
    counts = Counter(values)
    max_count = max(counts.values())
    top_values = [value for value, count in counts.items() if count == max_count]
    return max(top_values)


def _select_rating_candidates(
    candidates: tuple[StatisticCandidate, ...],
    *,
    target_instrument_name: str,
) -> tuple[StatisticCandidate, ...]:
    selected: list[StatisticCandidate] = []
    normalized_target = _normalize_instrument_name(target_instrument_name)

    for candidate in candidates:
        if candidate.evidence_source is EvidenceSourceType.CURRENT_STUDY:
            if not candidate.supports_direct_assessment:
                continue
        elif candidate.evidence_source is EvidenceSourceType.INTERPRETABILITY_ONLY:
            # Keep interpretability evidence only when it is instrument-scoped.
            if not candidate.instrument_name_hints:
                continue
            if (
                MeasurementPropertyRoute.INTERPRETABILITY
                not in candidate.measurement_property_routes
            ):
                continue
        else:
            continue
        if _is_excluded_for_target(candidate, normalized_target):
            continue
        selected.append(candidate)

    return tuple(selected)


def _is_excluded_for_target(
    candidate: StatisticCandidate,
    normalized_target: str,
) -> bool:
    instrument_hints = tuple(
        _normalize_instrument_name(hint) for hint in candidate.instrument_name_hints
    )
    comparator_hints = tuple(
        _normalize_instrument_name(hint) for hint in candidate.comparator_instrument_hints
    )

    if instrument_hints and not _hint_set_matches_target(
        target_name=normalized_target,
        hint_names=instrument_hints,
    ):
        return True

    return bool(
        comparator_hints
        and not _hint_set_matches_target(
            target_name=normalized_target,
            hint_names=instrument_hints,
        )
    )


def _hint_set_matches_target(*, target_name: str, hint_names: set[str] | tuple[str, ...]) -> bool:
    if not target_name or not hint_names:
        return False
    target_variants = _instrument_name_variants(target_name)
    return any(
        (_instrument_name_variants(hint_name) & target_variants)
        or _same_instrument_family_name(hint_name, target_name)
        for hint_name in hint_names
    )


def _instrument_name_variants(normalized_name: str) -> set[str]:
    cleaned = normalized_name.strip()
    if not cleaned:
        return set()
    variants = {cleaned}
    without_decimal_version = re.sub(r"\d+\.\d+$", "", cleaned)
    if without_decimal_version:
        variants.add(without_decimal_version)
    return {variant for variant in variants if variant}


def _same_instrument_family_name(first_name: str, second_name: str) -> bool:
    first = re.sub(r"[^A-Za-z0-9]", "", first_name).upper()
    second = re.sub(r"[^A-Za-z0-9]", "", second_name).upper()
    if not first or not second or first == second:
        return first == second and bool(first)

    shorter, longer = sorted((first, second), key=len)
    if len(shorter) < 3:
        return False
    if longer.startswith(shorter) and len(longer) - len(shorter) <= 6:
        return True

    common_prefix = len(os.path.commonprefix((first, second)))
    if common_prefix < 3:
        return False
    return len(first) - common_prefix <= 6 and len(second) - common_prefix <= 6


def _normalize_synthesis_inputs_by_instrument_family(
    synthesis_inputs: tuple[StudySynthesisInput, ...],
) -> tuple[StudySynthesisInput, ...]:
    grouped: dict[tuple[str, str], list[StudySynthesisInput]] = {}
    for entry in synthesis_inputs:
        grouped.setdefault((entry.study_id, entry.measurement_property), []).append(entry)

    drop_ids: set[str] = set()
    for entries in grouped.values():
        if len(entries) < 2:
            continue
        names = [entry.instrument_name for entry in entries]
        group_drop_ids = {
            entry.id
            for entry in entries
            if _is_family_base_instrument_name(entry.instrument_name, names)
        }
        if len(group_drop_ids) == len(entries):
            continue
        drop_ids.update(group_drop_ids)

    return tuple(entry for entry in synthesis_inputs if entry.id not in drop_ids)


def _is_family_base_instrument_name(name: str, peer_names: list[str]) -> bool:
    normalized_name = re.sub(r"[^A-Za-z0-9]", "", name).upper()
    if len(normalized_name) < 3:
        return False

    for peer in peer_names:
        if peer == name:
            continue
        normalized_peer = re.sub(r"[^A-Za-z0-9]", "", peer).upper()
        if len(normalized_peer) <= len(normalized_name):
            continue
        if not _same_instrument_family_name(name, peer):
            continue
        shared_prefix = len(os.path.commonprefix((normalized_name, normalized_peer)))
        if shared_prefix >= len(normalized_name):
            return True

    return False


def _normalize_instrument_name(value: str) -> str:
    normalized = value.strip().lower()
    aliases = {
        "sigam mobility scale": "sigam",
        "special interest group in amputee medicine": "sigam",
        "q tfa": "q-tfa",
        "questionnaire for persons with a transfemoral amputation": "q-tfa",
        "patient-reported outcomes measurement information system": "promis",
        "gait profile score": "gps",
        "two minute walk test": "2-mwt",
        "2mwt": "2-mwt",
    }
    mapped = aliases.get(normalized, normalized)
    return mapped.upper() if mapped in {"sigam", "promis"} else mapped.replace(" ", "").upper()


def _box3_inputs(
    *,
    statistic_candidates: tuple[StatisticCandidate, ...],
    sample_size: int | None,
    fallback_evidence_id: str,
) -> tuple[BoxItemInput, ...]:
    structural_stats = _select_stat_candidates(
        statistic_candidates,
        (StatisticType.CFI, StatisticType.TLI, StatisticType.RMSEA, StatisticType.SRMR),
    )
    has_structural_stat = bool(structural_stats)
    structural_evidence = _evidence_for_candidates(structural_stats, fallback_evidence_id)
    sample_rating = _sample_size_item_rating(sample_size)

    item_map = {
        BOX_3_ITEM_CODES[0]: BoxItemInput(
            item_code=BOX_3_ITEM_CODES[0],
            item_rating=(
                CosminItemRating.ADEQUATE if has_structural_stat else CosminItemRating.INADEQUATE
            ),
            evidence_span_ids=structural_evidence,
        ),
        BOX_3_ITEM_CODES[1]: BoxItemInput(
            item_code=BOX_3_ITEM_CODES[1],
            item_rating=CosminItemRating.NOT_APPLICABLE,
            evidence_span_ids=[fallback_evidence_id],
        ),
        BOX_3_ITEM_CODES[2]: BoxItemInput(
            item_code=BOX_3_ITEM_CODES[2],
            item_rating=sample_rating,
            evidence_span_ids=[fallback_evidence_id],
        ),
        BOX_3_ITEM_CODES[3]: BoxItemInput(
            item_code=BOX_3_ITEM_CODES[3],
            item_rating=CosminItemRating.VERY_GOOD,
            evidence_span_ids=[fallback_evidence_id],
        ),
    }
    return tuple(item_map[item_code] for item_code in BOX_3_ITEM_CODES)


def _box4_inputs(
    *,
    statistic_candidates: tuple[StatisticCandidate, ...],
    fallback_evidence_id: str,
) -> tuple[BoxItemInput, ...]:
    alpha_candidates = _select_stat_candidates(
        statistic_candidates,
        (StatisticType.CRONBACH_ALPHA,),
    )
    kr20_candidates = _select_stat_candidates(
        statistic_candidates,
        (StatisticType.KR20,),
    )
    has_alpha = bool(alpha_candidates)
    has_kr20 = bool(kr20_candidates)
    alpha_evidence = _evidence_for_candidates(alpha_candidates, fallback_evidence_id)
    kr20_evidence = _evidence_for_candidates(kr20_candidates, fallback_evidence_id)

    item_map = {
        BOX_4_ITEM_CODES[0]: BoxItemInput(
            item_code=BOX_4_ITEM_CODES[0],
            item_rating=(
                CosminItemRating.VERY_GOOD
                if has_alpha
                else (CosminItemRating.NOT_APPLICABLE if has_kr20 else CosminItemRating.INADEQUATE)
            ),
            evidence_span_ids=alpha_evidence,
        ),
        BOX_4_ITEM_CODES[1]: BoxItemInput(
            item_code=BOX_4_ITEM_CODES[1],
            item_rating=(
                CosminItemRating.VERY_GOOD
                if has_kr20
                else (CosminItemRating.NOT_APPLICABLE if has_alpha else CosminItemRating.INADEQUATE)
            ),
            evidence_span_ids=kr20_evidence,
        ),
        BOX_4_ITEM_CODES[2]: BoxItemInput(
            item_code=BOX_4_ITEM_CODES[2],
            item_rating=CosminItemRating.NOT_APPLICABLE,
            evidence_span_ids=[fallback_evidence_id],
        ),
        BOX_4_ITEM_CODES[3]: BoxItemInput(
            item_code=BOX_4_ITEM_CODES[3],
            item_rating=CosminItemRating.VERY_GOOD,
            evidence_span_ids=[fallback_evidence_id],
        ),
    }
    return tuple(item_map[item_code] for item_code in BOX_4_ITEM_CODES)


def _box5_inputs(
    *,
    statistic_candidates: tuple[StatisticCandidate, ...],
    fallback_evidence_id: str,
) -> tuple[BoxItemInput, ...]:
    invariance_candidates = _select_stat_candidates(
        statistic_candidates,
        (StatisticType.MEASUREMENT_INVARIANCE_FINDING,),
    )
    has_invariance = bool(invariance_candidates)
    evidence = _evidence_for_candidates(invariance_candidates, fallback_evidence_id)

    return tuple(
        BoxItemInput(
            item_code=item_code,
            item_rating=CosminItemRating.ADEQUATE if has_invariance else CosminItemRating.DOUBTFUL,
            evidence_span_ids=evidence,
        )
        for item_code in BOX_5_ITEM_CODES
    )


def _box6_inputs(
    *,
    statistic_candidates: tuple[StatisticCandidate, ...],
    fallback_evidence_id: str,
    follow_up_interval: ContextFieldExtraction | None = None,
) -> tuple[BoxItemInput, ...]:
    icc_candidates = _select_stat_candidates(statistic_candidates, (StatisticType.ICC,))
    weighted_kappa_candidates = _select_stat_candidates(
        statistic_candidates,
        (StatisticType.WEIGHTED_KAPPA,),
    )
    kappa_candidates = _select_stat_candidates(
        statistic_candidates,
        (StatisticType.KAPPA,),
    )
    icc_evidence = _evidence_for_candidates(icc_candidates, fallback_evidence_id)
    weighted_kappa_evidence = _evidence_for_candidates(
        weighted_kappa_candidates,
        fallback_evidence_id,
    )
    kappa_evidence = _evidence_for_candidates(
        kappa_candidates,
        fallback_evidence_id,
    )
    has_any_kappa = bool(weighted_kappa_candidates or kappa_candidates)
    dichotomous_kappa_candidates = tuple(
        candidate
        for candidate in kappa_candidates
        if _kappa_matches_dimension(candidate, "dichotomous")
    )
    nominal_kappa_candidates = tuple(
        candidate
        for candidate in kappa_candidates
        if _kappa_matches_dimension(candidate, "nominal")
    )
    generic_kappa_candidates = tuple(
        candidate
        for candidate in kappa_candidates
        if candidate not in dichotomous_kappa_candidates
        and candidate not in nominal_kappa_candidates
    )
    design_item_ratings = _box6_design_item_ratings(
        statistic_candidates=statistic_candidates,
        follow_up_interval=follow_up_interval,
        fallback_evidence_id=fallback_evidence_id,
    )

    item_map = {
        BOX_6_ITEM_CODES[0]: BoxItemInput(
            item_code=BOX_6_ITEM_CODES[0],
            item_rating=design_item_ratings[BOX_6_ITEM_CODES[0]][0],
            evidence_span_ids=design_item_ratings[BOX_6_ITEM_CODES[0]][1],
        ),
        BOX_6_ITEM_CODES[1]: BoxItemInput(
            item_code=BOX_6_ITEM_CODES[1],
            item_rating=design_item_ratings[BOX_6_ITEM_CODES[1]][0],
            evidence_span_ids=design_item_ratings[BOX_6_ITEM_CODES[1]][1],
        ),
        BOX_6_ITEM_CODES[2]: BoxItemInput(
            item_code=BOX_6_ITEM_CODES[2],
            item_rating=design_item_ratings[BOX_6_ITEM_CODES[2]][0],
            evidence_span_ids=design_item_ratings[BOX_6_ITEM_CODES[2]][1],
        ),
        BOX_6_ITEM_CODES[3]: BoxItemInput(
            item_code=BOX_6_ITEM_CODES[3],
            item_rating=(
                CosminItemRating.ADEQUATE
                if icc_candidates
                else (
                    CosminItemRating.NOT_APPLICABLE
                    if has_any_kappa
                    else CosminItemRating.INADEQUATE
                )
            ),
            evidence_span_ids=icc_evidence,
        ),
        BOX_6_ITEM_CODES[4]: BoxItemInput(
            item_code=BOX_6_ITEM_CODES[4],
            item_rating=(
                CosminItemRating.ADEQUATE
                if dichotomous_kappa_candidates
                else (
                    CosminItemRating.DOUBTFUL
                    if generic_kappa_candidates
                    else CosminItemRating.NOT_APPLICABLE
                )
            ),
            evidence_span_ids=(
                _evidence_for_candidates(dichotomous_kappa_candidates, fallback_evidence_id)
                if dichotomous_kappa_candidates
                else kappa_evidence
            ),
        ),
        BOX_6_ITEM_CODES[5]: BoxItemInput(
            item_code=BOX_6_ITEM_CODES[5],
            item_rating=(
                CosminItemRating.ADEQUATE
                if nominal_kappa_candidates
                else CosminItemRating.NOT_APPLICABLE
            ),
            evidence_span_ids=(
                _evidence_for_candidates(nominal_kappa_candidates, fallback_evidence_id)
                if nominal_kappa_candidates
                else [fallback_evidence_id]
            ),
        ),
        BOX_6_ITEM_CODES[6]: BoxItemInput(
            item_code=BOX_6_ITEM_CODES[6],
            item_rating=(
                CosminItemRating.ADEQUATE
                if weighted_kappa_candidates
                else CosminItemRating.NOT_APPLICABLE
            ),
            evidence_span_ids=weighted_kappa_evidence,
        ),
        BOX_6_ITEM_CODES[7]: BoxItemInput(
            item_code=BOX_6_ITEM_CODES[7],
            item_rating=CosminItemRating.VERY_GOOD,
            evidence_span_ids=[fallback_evidence_id],
        ),
    }
    return tuple(item_map[item_code] for item_code in BOX_6_ITEM_CODES)


def _box7_inputs(
    *,
    statistic_candidates: tuple[StatisticCandidate, ...],
    fallback_evidence_id: str,
) -> tuple[BoxItemInput, ...]:
    support = _select_stat_candidates(
        statistic_candidates,
        (StatisticType.SEM, StatisticType.SDC, StatisticType.LOA, StatisticType.MIC),
    )
    has_support = bool(support)
    evidence = _evidence_for_candidates(support, fallback_evidence_id)
    return tuple(
        BoxItemInput(
            item_code=item_code,
            item_rating=CosminItemRating.ADEQUATE if has_support else CosminItemRating.DOUBTFUL,
            evidence_span_ids=evidence,
        )
        for item_code in BOX_7_ITEM_CODES
    )


def _box8_inputs(
    *,
    statistic_candidates: tuple[StatisticCandidate, ...],
    fallback_evidence_id: str,
) -> tuple[BoxItemInput, ...]:
    relevant = _select_stat_candidates(
        statistic_candidates,
        (StatisticType.CORRELATION, StatisticType.AUC),
    )
    has_relevant = bool(relevant)
    evidence = _evidence_for_candidates(relevant, fallback_evidence_id)
    return tuple(
        BoxItemInput(
            item_code=item_code,
            item_rating=CosminItemRating.ADEQUATE if has_relevant else CosminItemRating.DOUBTFUL,
            evidence_span_ids=evidence,
        )
        for item_code in BOX_8_ITEM_CODES
    )


def _box9_inputs(
    *,
    statistic_candidates: tuple[StatisticCandidate, ...],
    fallback_evidence_id: str,
) -> tuple[BoxItemInput, ...]:
    relevant = _select_stat_candidates(
        statistic_candidates,
        (
            StatisticType.CORRELATION,
            StatisticType.AUC,
            StatisticType.KNOWN_GROUPS_OR_COMPARATOR_RESULT,
        ),
    )
    evidence = _evidence_for_candidates(relevant, fallback_evidence_id)
    has_relevant = bool(relevant)
    hypotheses_predefined = any(
        "a priori" in candidate.surrounding_text.lower() for candidate in relevant
    )

    item_map = {
        BOX_9_ITEM_CODES[0]: BoxItemInput(
            item_code=BOX_9_ITEM_CODES[0],
            item_rating=(
                CosminItemRating.ADEQUATE if hypotheses_predefined else CosminItemRating.DOUBTFUL
            ),
            evidence_span_ids=evidence,
        ),
        BOX_9_ITEM_CODES[1]: BoxItemInput(
            item_code=BOX_9_ITEM_CODES[1],
            item_rating=CosminItemRating.DOUBTFUL,
            evidence_span_ids=evidence,
        ),
        BOX_9_ITEM_CODES[2]: BoxItemInput(
            item_code=BOX_9_ITEM_CODES[2],
            item_rating=CosminItemRating.ADEQUATE if has_relevant else CosminItemRating.DOUBTFUL,
            evidence_span_ids=evidence,
        ),
        BOX_9_ITEM_CODES[3]: BoxItemInput(
            item_code=BOX_9_ITEM_CODES[3],
            item_rating=CosminItemRating.ADEQUATE if has_relevant else CosminItemRating.DOUBTFUL,
            evidence_span_ids=evidence,
        ),
        BOX_9_ITEM_CODES[4]: BoxItemInput(
            item_code=BOX_9_ITEM_CODES[4],
            item_rating=CosminItemRating.VERY_GOOD,
            evidence_span_ids=[fallback_evidence_id],
        ),
    }
    return tuple(item_map[item_code] for item_code in BOX_9_ITEM_CODES)


def _box10_inputs(
    *,
    statistic_candidates: tuple[StatisticCandidate, ...],
    fallback_evidence_id: str,
) -> tuple[BoxItemInput, ...]:
    relevant = _select_stat_candidates(
        statistic_candidates,
        (StatisticType.RESPONSIVENESS_RELATED_STATISTIC, StatisticType.AUC),
    )
    evidence = _evidence_for_candidates(relevant, fallback_evidence_id)
    has_relevant = bool(relevant)
    hypotheses_predefined = any(
        candidate.responsiveness_hypothesis_status is ResponsivenessHypothesisStatus.PREDEFINED
        for candidate in relevant
    )

    item_map = {
        BOX_10_ITEM_CODES[0]: BoxItemInput(
            item_code=BOX_10_ITEM_CODES[0],
            item_rating=(
                CosminItemRating.ADEQUATE if hypotheses_predefined else CosminItemRating.DOUBTFUL
            ),
            evidence_span_ids=evidence,
        ),
        BOX_10_ITEM_CODES[1]: BoxItemInput(
            item_code=BOX_10_ITEM_CODES[1],
            item_rating=CosminItemRating.ADEQUATE if has_relevant else CosminItemRating.DOUBTFUL,
            evidence_span_ids=evidence,
        ),
        BOX_10_ITEM_CODES[2]: BoxItemInput(
            item_code=BOX_10_ITEM_CODES[2],
            item_rating=CosminItemRating.ADEQUATE if has_relevant else CosminItemRating.DOUBTFUL,
            evidence_span_ids=evidence,
        ),
        BOX_10_ITEM_CODES[3]: BoxItemInput(
            item_code=BOX_10_ITEM_CODES[3],
            item_rating=CosminItemRating.ADEQUATE if has_relevant else CosminItemRating.DOUBTFUL,
            evidence_span_ids=evidence,
        ),
        BOX_10_ITEM_CODES[4]: BoxItemInput(
            item_code=BOX_10_ITEM_CODES[4],
            item_rating=CosminItemRating.VERY_GOOD,
            evidence_span_ids=[fallback_evidence_id],
        ),
    }
    return tuple(item_map[item_code] for item_code in BOX_10_ITEM_CODES)


def _kappa_matches_dimension(candidate: StatisticCandidate, dimension: str) -> bool:
    text = candidate.surrounding_text.lower()
    if dimension == "dichotomous":
        return "dichotom" in text or "cohen" in text
    if dimension == "nominal":
        return "nominal" in text
    return False


def _box6_design_item_ratings(
    *,
    statistic_candidates: tuple[StatisticCandidate, ...],
    follow_up_interval: ContextFieldExtraction | None,
    fallback_evidence_id: str,
) -> dict[str, tuple[CosminItemRating, list[str]]]:
    if not statistic_candidates:
        return {
            BOX_6_ITEM_CODES[0]: (CosminItemRating.DOUBTFUL, [fallback_evidence_id]),
            BOX_6_ITEM_CODES[1]: (CosminItemRating.DOUBTFUL, [fallback_evidence_id]),
            BOX_6_ITEM_CODES[2]: (CosminItemRating.DOUBTFUL, [fallback_evidence_id]),
        }

    evidence_ids = list(_evidence_for_candidates(statistic_candidates, fallback_evidence_id))
    follow_up_evidence_ids = list(_field_evidence_span_ids(follow_up_interval))
    text_blob = " ".join(candidate.surrounding_text.lower() for candidate in statistic_candidates)

    has_retest_design = any(
        token in text_blob
        for token in ("test-retest", "retest", "first and second", "second administration")
    )
    has_stability_signal = "stable" in text_blob and "non-stable" not in text_blob
    has_interval_signal = bool(
        re.search(r"\b\d+\s*(day|days|week|weeks|month|months|year|years)\b", text_blob)
    ) or bool(follow_up_evidence_ids)
    has_condition_signal = any(
        token in text_blob
        for token in (
            "same conditions",
            "same assessor",
            "same protocol",
            "same questionnaire",
            "first and second administrations",
        )
    )

    stability_rating = (
        CosminItemRating.ADEQUATE
        if has_stability_signal
        else (CosminItemRating.DOUBTFUL if has_retest_design else CosminItemRating.INADEQUATE)
    )
    interval_rating = (
        CosminItemRating.ADEQUATE
        if has_interval_signal
        else (CosminItemRating.DOUBTFUL if has_retest_design else CosminItemRating.INADEQUATE)
    )
    conditions_rating = (
        CosminItemRating.ADEQUATE
        if has_condition_signal
        else (CosminItemRating.DOUBTFUL if has_retest_design else CosminItemRating.INADEQUATE)
    )

    interval_evidence = evidence_ids + [
        evidence_id for evidence_id in follow_up_evidence_ids if evidence_id not in evidence_ids
    ]
    return {
        BOX_6_ITEM_CODES[0]: (stability_rating, evidence_ids),
        BOX_6_ITEM_CODES[1]: (interval_rating, interval_evidence or evidence_ids),
        BOX_6_ITEM_CODES[2]: (conditions_rating, evidence_ids),
    }


def _select_most_conservative_box_bundle(
    bundles: tuple[BoxAssessmentBundle, ...],
) -> BoxAssessmentBundle | None:
    if not bundles:
        return None

    order = {
        CosminBoxRating.INADEQUATE: 0,
        CosminBoxRating.DOUBTFUL: 1,
        CosminBoxRating.INDETERMINATE: 2,
        CosminBoxRating.ADEQUATE: 3,
        CosminBoxRating.VERY_GOOD: 4,
    }
    return min(bundles, key=lambda bundle: order[bundle.box_assessment.box_rating])


def _structural_validity_prerequisite(
    structural_result: MeasurementPropertyRatingResult | None,
) -> PrerequisiteDecision:
    if structural_result is None:
        return PrerequisiteDecision(
            name=REQUIRED_PREREQUISITE_NAME,
            status=PrerequisiteStatus.MISSING,
            detail="No direct structural-validity result was available for prerequisite chaining.",
            evidence_span_ids=(),
        )

    if structural_result.computed_rating is MeasurementPropertyRating.SUFFICIENT:
        status = PrerequisiteStatus.MET
    elif structural_result.computed_rating is MeasurementPropertyRating.INDETERMINATE:
        status = PrerequisiteStatus.MISSING
    else:
        status = PrerequisiteStatus.NOT_MET

    return PrerequisiteDecision(
        name=REQUIRED_PREREQUISITE_NAME,
        status=status,
        detail=(
            "Derived from structural validity rating: " f"{structural_result.computed_rating.value}"
        ),
        evidence_span_ids=structural_result.evidence_span_ids,
    )


def _risk_of_bias_input(
    *,
    box_bundle: BoxAssessmentBundle | None,
    fallback_evidence_id: str,
) -> DomainDowngradeInput:
    if box_bundle is None:
        return DomainDowngradeInput(
            domain=ModifiedGradeDomain.RISK_OF_BIAS,
            severity=DowngradeSeverity.SERIOUS,
            reason="No matching COSMIN RoB box was available for this property.",
            evidence_span_ids=(fallback_evidence_id,),
            explanation=(
                "Applied a serious risk-of-bias downgrade due to missing box-level evidence."
            ),
        )

    box_rating = box_bundle.box_assessment.box_rating
    if box_rating in {CosminBoxRating.VERY_GOOD, CosminBoxRating.ADEQUATE}:
        return DomainDowngradeInput(
            domain=ModifiedGradeDomain.RISK_OF_BIAS,
            severity=DowngradeSeverity.NONE,
            reason=None,
            evidence_span_ids=(),
            explanation=None,
        )

    if box_rating is CosminBoxRating.INADEQUATE:
        severity = DowngradeSeverity.VERY_SERIOUS
    else:
        severity = DowngradeSeverity.SERIOUS

    return DomainDowngradeInput(
        domain=ModifiedGradeDomain.RISK_OF_BIAS,
        severity=severity,
        reason=f"RoB box rating was {box_rating.value}.",
        evidence_span_ids=tuple(box_bundle.box_assessment.evidence_span_ids)
        or (fallback_evidence_id,),
        explanation=(
            "Applied risk-of-bias downgrade based on provisional mapping from "
            "box-level methodological quality."
        ),
    )


def _grade_skipped_result(
    *,
    synthesis_result: SynthesisAggregateResult,
    reason: str,
) -> ModifiedGradeResult:
    none_decisions = (
        DomainDowngradeInput(
            domain=ModifiedGradeDomain.RISK_OF_BIAS,
            severity=DowngradeSeverity.NONE,
            reason=None,
            evidence_span_ids=(),
            explanation=None,
        ),
        DomainDowngradeInput(
            domain=ModifiedGradeDomain.INCONSISTENCY,
            severity=DowngradeSeverity.NONE,
            reason=None,
            evidence_span_ids=(),
            explanation=None,
        ),
        DomainDowngradeInput(
            domain=ModifiedGradeDomain.IMPRECISION,
            severity=DowngradeSeverity.NONE,
            reason=None,
            evidence_span_ids=(),
            explanation=None,
        ),
        DomainDowngradeInput(
            domain=ModifiedGradeDomain.INDIRECTNESS,
            severity=DowngradeSeverity.NONE,
            reason=None,
            evidence_span_ids=(),
            explanation=None,
        ),
    )
    return ModifiedGradeResult(
        id=_stable_id(
            "grade",
            synthesis_result.id,
            synthesis_result.measurement_property,
            synthesis_result.activation_status.value,
            "skipped",
        ),
        synthesis_id=synthesis_result.id,
        measurement_property=synthesis_result.measurement_property,
        starting_certainty=EvidenceCertaintyLevel.HIGH,
        final_certainty=EvidenceCertaintyLevel.HIGH,
        total_downgrade_steps=0,
        total_sample_size=synthesis_result.total_sample_size,
        domain_decisions=none_decisions,
        downgrade_records=(),
        evidence_span_ids=synthesis_result.evidence_span_ids,
        explanation=reason,
        activation_status=synthesis_result.activation_status,
        grade_executed=False,
    )


def _sample_size_item_rating(sample_size: int | None) -> CosminItemRating:
    if sample_size is None:
        return CosminItemRating.DOUBTFUL
    if sample_size >= 100:
        return CosminItemRating.ADEQUATE
    if sample_size >= 50:
        return CosminItemRating.DOUBTFUL
    return CosminItemRating.INADEQUATE


def _select_stat_candidates(
    candidates: tuple[StatisticCandidate, ...],
    types: tuple[StatisticType, ...],
) -> tuple[StatisticCandidate, ...]:
    allowed = set(types)
    return tuple(candidate for candidate in candidates if candidate.statistic_type in allowed)


def _evidence_for_candidates(
    candidates: tuple[StatisticCandidate, ...],
    fallback_evidence_id: str,
) -> list[str]:
    evidence_ids = sorted(
        {span_id for candidate in candidates for span_id in candidate.evidence_span_ids}
    )
    if evidence_ids:
        return evidence_ids
    return [fallback_evidence_id]


def _first_string_value(field: ContextFieldExtraction) -> str | None:
    if field.status is not FieldDetectionStatus.DETECTED:
        return None
    value = field.candidates[0].normalized_value
    if isinstance(value, str):
        return value
    return None


def _first_int_value(field: ContextFieldExtraction) -> int | None:
    if field.status is not FieldDetectionStatus.DETECTED:
        return None
    value = field.candidates[0].normalized_value
    if isinstance(value, int):
        return value
    return None


def _fallback_evidence_id(parsed: ParsedMarkdownDocument) -> str:
    if parsed.sentences:
        return parsed.sentences[0].id
    if parsed.paragraphs:
        return parsed.paragraphs[0].id
    if parsed.headings:
        return parsed.headings[0].id
    return _stable_id("fallback", parsed.id, parsed.file_path)


def _stable_id(prefix: str, *parts: object) -> str:
    serialized = "|".join(str(part) for part in parts)
    digest = hashlib.sha1(f"{prefix}|{serialized}".encode()).hexdigest()[:16]
    return f"{prefix}.{digest}"
