"""Provisional end-to-end assessment pipeline orchestration."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from cosmin_assistant.cosmin_rob import (
    BOX_3_ITEM_CODES,
    BOX_4_ITEM_CODES,
    BOX_6_ITEM_CODES,
    BoxAssessmentBundle,
    BoxItemInput,
    assess_box3_structural_validity,
    assess_box4_internal_consistency,
    assess_box6_reliability,
)
from cosmin_assistant.extract import (
    ArticleContextExtractionResult,
    ArticleStatisticsExtractionResult,
    ContextFieldExtraction,
    FieldDetectionStatus,
    ParsedMarkdownDocument,
    StatisticCandidate,
    StatisticType,
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
    REQUIRED_PREREQUISITE_NAME,
    MeasurementPropertyRatingResult,
    PrerequisiteDecision,
    PrerequisiteStatus,
    rate_internal_consistency,
    rate_reliability,
    rate_structural_validity,
)
from cosmin_assistant.models import (
    CosminBoxRating,
    CosminItemRating,
    MeasurementPropertyRating,
    ProfileType,
)
from cosmin_assistant.profiles import get_profile
from cosmin_assistant.synthesize import (
    StudySynthesisInput,
    SynthesisAggregateResult,
    synthesize_first_pass,
)


@dataclass(frozen=True)
class ProvisionalAssessmentRun:
    """Structured in-memory artifacts for one provisional end-to-end run."""

    article_path: str
    profile_type: ProfileType
    parsed_document: ParsedMarkdownDocument
    context_extraction: ArticleContextExtractionResult
    statistics_extraction: ArticleStatisticsExtractionResult
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

    study_id = context.study_contexts[0].study_id
    instrument_id = context.instrument_contexts[0].instrument_id
    sample_size = _first_int_value(context.study_contexts[0].sample_sizes)

    rob_assessments = _build_provisional_rob_assessments(
        study_id=study_id,
        instrument_id=instrument_id,
        statistic_candidates=statistics.candidates,
        sample_size=sample_size,
        fallback_evidence_id=fallback_evidence_id,
    )

    structural = rate_structural_validity(
        study_id=study_id,
        instrument_id=instrument_id,
        statistic_candidates=statistics.candidates,
    )
    prerequisite = _structural_validity_prerequisite(structural)
    internal = rate_internal_consistency(
        study_id=study_id,
        instrument_id=instrument_id,
        statistic_candidates=statistics.candidates,
        prerequisite_decisions=(prerequisite,),
    )
    reliability = rate_reliability(
        study_id=study_id,
        instrument_id=instrument_id,
        statistic_candidates=statistics.candidates,
    )
    measurement_results = (structural, internal, reliability)

    instrument_name = (
        _first_string_value(context.instrument_contexts[0].instrument_name) or "unknown"
    )
    instrument_version = _first_string_value(context.instrument_contexts[0].instrument_version)
    subscale = _first_string_value(context.instrument_contexts[0].subscale)

    synthesis_inputs = tuple(
        StudySynthesisInput(
            id=result.id,
            study_id=result.study_id,
            instrument_name=instrument_name,
            instrument_version=instrument_version,
            subscale=subscale,
            measurement_property=result.measurement_property,
            rating=result.computed_rating,
            sample_size=sample_size,
            evidence_span_ids=result.evidence_span_ids or (fallback_evidence_id,),
            study_explanation=result.explanation,
        )
        for result in measurement_results
    )
    synthesis_results = synthesize_first_pass(synthesis_inputs)

    rob_by_property = {
        bundle.box_assessment.measurement_property: bundle for bundle in rob_assessments
    }
    grade_results = tuple(
        apply_modified_grade(
            synthesis_result=synthesis_result,
            risk_of_bias=_risk_of_bias_input(
                box_bundle=rob_by_property.get(synthesis_result.measurement_property),
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
        for synthesis_result in synthesis_results
    )

    return ProvisionalAssessmentRun(
        article_path=str(Path(article_path).resolve()),
        profile_type=resolved_profile,
        parsed_document=parsed,
        context_extraction=context,
        statistics_extraction=statistics,
        rob_assessments=rob_assessments,
        measurement_property_results=measurement_results,
        synthesis_results=synthesis_results,
        grade_results=grade_results,
    )


def _build_provisional_rob_assessments(
    *,
    study_id: str,
    instrument_id: str,
    statistic_candidates: tuple[StatisticCandidate, ...],
    sample_size: int | None,
    fallback_evidence_id: str,
) -> tuple[BoxAssessmentBundle, ...]:
    box3 = assess_box3_structural_validity(
        study_id=study_id,
        instrument_id=instrument_id,
        item_inputs=_box3_inputs(
            statistic_candidates=statistic_candidates,
            sample_size=sample_size,
            fallback_evidence_id=fallback_evidence_id,
        ),
    )
    box4 = assess_box4_internal_consistency(
        study_id=study_id,
        instrument_id=instrument_id,
        item_inputs=_box4_inputs(
            statistic_candidates=statistic_candidates,
            fallback_evidence_id=fallback_evidence_id,
        ),
    )
    box6 = assess_box6_reliability(
        study_id=study_id,
        instrument_id=instrument_id,
        item_inputs=_box6_inputs(
            statistic_candidates=statistic_candidates,
            fallback_evidence_id=fallback_evidence_id,
        ),
    )
    return (box3, box4, box6)


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
    has_alpha = bool(alpha_candidates)
    alpha_evidence = _evidence_for_candidates(alpha_candidates, fallback_evidence_id)

    item_map = {
        BOX_4_ITEM_CODES[0]: BoxItemInput(
            item_code=BOX_4_ITEM_CODES[0],
            item_rating=CosminItemRating.VERY_GOOD if has_alpha else CosminItemRating.INADEQUATE,
            evidence_span_ids=alpha_evidence,
        ),
        BOX_4_ITEM_CODES[1]: BoxItemInput(
            item_code=BOX_4_ITEM_CODES[1],
            item_rating=CosminItemRating.NOT_APPLICABLE,
            evidence_span_ids=[fallback_evidence_id],
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


def _box6_inputs(
    *,
    statistic_candidates: tuple[StatisticCandidate, ...],
    fallback_evidence_id: str,
) -> tuple[BoxItemInput, ...]:
    icc_candidates = _select_stat_candidates(statistic_candidates, (StatisticType.ICC,))
    weighted_kappa_candidates = _select_stat_candidates(
        statistic_candidates,
        (StatisticType.WEIGHTED_KAPPA,),
    )
    icc_evidence = _evidence_for_candidates(icc_candidates, fallback_evidence_id)
    weighted_kappa_evidence = _evidence_for_candidates(
        weighted_kappa_candidates,
        fallback_evidence_id,
    )

    item_map = {
        BOX_6_ITEM_CODES[0]: BoxItemInput(
            item_code=BOX_6_ITEM_CODES[0],
            item_rating=CosminItemRating.DOUBTFUL,
            evidence_span_ids=[fallback_evidence_id],
        ),
        BOX_6_ITEM_CODES[1]: BoxItemInput(
            item_code=BOX_6_ITEM_CODES[1],
            item_rating=CosminItemRating.DOUBTFUL,
            evidence_span_ids=[fallback_evidence_id],
        ),
        BOX_6_ITEM_CODES[2]: BoxItemInput(
            item_code=BOX_6_ITEM_CODES[2],
            item_rating=CosminItemRating.DOUBTFUL,
            evidence_span_ids=[fallback_evidence_id],
        ),
        BOX_6_ITEM_CODES[3]: BoxItemInput(
            item_code=BOX_6_ITEM_CODES[3],
            item_rating=(
                CosminItemRating.ADEQUATE if icc_candidates else CosminItemRating.INADEQUATE
            ),
            evidence_span_ids=icc_evidence,
        ),
        BOX_6_ITEM_CODES[4]: BoxItemInput(
            item_code=BOX_6_ITEM_CODES[4],
            item_rating=CosminItemRating.NOT_APPLICABLE,
            evidence_span_ids=[fallback_evidence_id],
        ),
        BOX_6_ITEM_CODES[5]: BoxItemInput(
            item_code=BOX_6_ITEM_CODES[5],
            item_rating=CosminItemRating.NOT_APPLICABLE,
            evidence_span_ids=[fallback_evidence_id],
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


def _structural_validity_prerequisite(
    structural_result: MeasurementPropertyRatingResult,
) -> PrerequisiteDecision:
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
                "Applied a serious risk-of-bias downgrade due to missing " "box-level evidence."
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
