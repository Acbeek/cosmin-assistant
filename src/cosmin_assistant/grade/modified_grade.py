"""Deterministic modified GRADE implementation for first-pass synthesis."""

from __future__ import annotations

import hashlib

from cosmin_assistant.grade.models import (
    DomainDowngradeInput,
    DomainDowngradeRecord,
    DowngradeSeverity,
    ModifiedGradeDomain,
    ModifiedGradeResult,
)
from cosmin_assistant.models import EvidenceCertaintyLevel, StableId
from cosmin_assistant.synthesize import SynthesisAggregateResult

STARTING_CERTAINTY = EvidenceCertaintyLevel.HIGH
RULE_NAME_MODIFIED_GRADE = "GRADE_MODIFIED_PROM_V1"

_CERTAINTY_ORDER: tuple[EvidenceCertaintyLevel, ...] = (
    EvidenceCertaintyLevel.HIGH,
    EvidenceCertaintyLevel.MODERATE,
    EvidenceCertaintyLevel.LOW,
    EvidenceCertaintyLevel.VERY_LOW,
)

_SEVERITY_STEPS: dict[DowngradeSeverity, int] = {
    DowngradeSeverity.NONE: 0,
    DowngradeSeverity.SERIOUS: 1,
    DowngradeSeverity.VERY_SERIOUS: 2,
    DowngradeSeverity.EXTREMELY_SERIOUS: 3,
}

_ALLOWED_SEVERITIES: dict[ModifiedGradeDomain, set[DowngradeSeverity]] = {
    ModifiedGradeDomain.RISK_OF_BIAS: {
        DowngradeSeverity.NONE,
        DowngradeSeverity.SERIOUS,
        DowngradeSeverity.VERY_SERIOUS,
        DowngradeSeverity.EXTREMELY_SERIOUS,
    },
    ModifiedGradeDomain.INCONSISTENCY: {
        DowngradeSeverity.NONE,
        DowngradeSeverity.SERIOUS,
        DowngradeSeverity.VERY_SERIOUS,
    },
    ModifiedGradeDomain.IMPRECISION: {
        DowngradeSeverity.NONE,
        DowngradeSeverity.SERIOUS,
        DowngradeSeverity.VERY_SERIOUS,
    },
    ModifiedGradeDomain.INDIRECTNESS: {
        DowngradeSeverity.NONE,
        DowngradeSeverity.SERIOUS,
        DowngradeSeverity.VERY_SERIOUS,
    },
}


def apply_modified_grade(
    *,
    synthesis_result: SynthesisAggregateResult,
    risk_of_bias: DomainDowngradeInput,
    indirectness: DomainDowngradeInput,
    inconsistency: DomainDowngradeInput | None = None,
) -> ModifiedGradeResult:
    """Apply modified GRADE downgrading from HIGH certainty."""

    _validate_domain_input(risk_of_bias, expected_domain=ModifiedGradeDomain.RISK_OF_BIAS)
    _validate_domain_input(indirectness, expected_domain=ModifiedGradeDomain.INDIRECTNESS)

    inconsistency_input = inconsistency or default_inconsistency_input(synthesis_result)
    _validate_domain_input(
        inconsistency_input,
        expected_domain=ModifiedGradeDomain.INCONSISTENCY,
    )
    imprecision_input = derive_imprecision_input(
        total_sample_size=synthesis_result.total_sample_size,
        evidence_span_ids=synthesis_result.evidence_span_ids,
    )

    domain_decisions = (
        risk_of_bias,
        inconsistency_input,
        imprecision_input,
        indirectness,
    )

    current_certainty = STARTING_CERTAINTY
    records: list[DomainDowngradeRecord] = []
    for decision in domain_decisions:
        steps = _SEVERITY_STEPS[decision.severity]
        if steps == 0:
            continue
        certainty_before = current_certainty
        current_certainty = _downgrade_certainty(current_certainty, steps)
        records.append(
            DomainDowngradeRecord(
                id=_stable_id(
                    "grade.domain",
                    synthesis_result.id,
                    decision.domain.value,
                    decision.severity.value,
                    decision.reason,
                    ",".join(decision.evidence_span_ids),
                ),
                domain=decision.domain,
                severity=decision.severity,
                downgrade_steps=steps,
                reason=decision.reason or "unspecified",
                evidence_span_ids=decision.evidence_span_ids,
                explanation=decision.explanation or "unspecified",
                certainty_before=certainty_before,
                certainty_after=current_certainty,
            )
        )

    evidence_span_ids = tuple(
        sorted({span_id for decision in domain_decisions for span_id in decision.evidence_span_ids})
    )
    total_steps = sum(record.downgrade_steps for record in records)
    explanation = _build_explanation(records)

    return ModifiedGradeResult(
        id=_stable_id(
            "grade",
            synthesis_result.id,
            synthesis_result.measurement_property,
            STARTING_CERTAINTY.value,
            current_certainty.value,
            RULE_NAME_MODIFIED_GRADE,
        ),
        synthesis_id=synthesis_result.id,
        measurement_property=synthesis_result.measurement_property,
        starting_certainty=STARTING_CERTAINTY,
        final_certainty=current_certainty,
        total_downgrade_steps=total_steps,
        total_sample_size=synthesis_result.total_sample_size,
        domain_decisions=domain_decisions,
        downgrade_records=tuple(records),
        evidence_span_ids=evidence_span_ids,
        explanation=explanation,
    )


def derive_imprecision_input(
    *,
    total_sample_size: int | None,
    evidence_span_ids: tuple[StableId, ...],
) -> DomainDowngradeInput:
    """Derive imprecision downgrade from total sample size.

    Based on modified GRADE Table S2 thresholds:
    - serious (-1): total n = 50-100
    - very serious (-2): total n < 50
    """

    if total_sample_size is None:
        return DomainDowngradeInput(
            domain=ModifiedGradeDomain.IMPRECISION,
            severity=DowngradeSeverity.SERIOUS,
            reason="Total sample size was not reported.",
            evidence_span_ids=evidence_span_ids,
            explanation="Imprecision downgraded by 1 level because total n is unavailable.",
        )

    if total_sample_size < 50:
        return DomainDowngradeInput(
            domain=ModifiedGradeDomain.IMPRECISION,
            severity=DowngradeSeverity.VERY_SERIOUS,
            reason="Total sample size was below 50.",
            evidence_span_ids=evidence_span_ids,
            explanation="Imprecision downgraded by 2 levels because total n < 50.",
        )

    if 50 <= total_sample_size <= 100:
        return DomainDowngradeInput(
            domain=ModifiedGradeDomain.IMPRECISION,
            severity=DowngradeSeverity.SERIOUS,
            reason="Total sample size was between 50 and 100.",
            evidence_span_ids=evidence_span_ids,
            explanation="Imprecision downgraded by 1 level because total n is 50-100.",
        )

    return DomainDowngradeInput(
        domain=ModifiedGradeDomain.IMPRECISION,
        severity=DowngradeSeverity.NONE,
        reason=None,
        evidence_span_ids=(),
        explanation=None,
    )


def default_inconsistency_input(
    synthesis_result: SynthesisAggregateResult,
) -> DomainDowngradeInput:
    """Build default inconsistency domain input from synthesis state."""

    if synthesis_result.inconsistent_findings:
        return DomainDowngradeInput(
            domain=ModifiedGradeDomain.INCONSISTENCY,
            severity=DowngradeSeverity.SERIOUS,
            reason="Synthesized study findings were inconsistent.",
            evidence_span_ids=synthesis_result.evidence_span_ids,
            explanation=(
                "Inconsistency downgraded by 1 level because synthesis retained "
                "conflicting sufficient and insufficient findings."
            ),
        )

    return DomainDowngradeInput(
        domain=ModifiedGradeDomain.INCONSISTENCY,
        severity=DowngradeSeverity.NONE,
        reason=None,
        evidence_span_ids=(),
        explanation=None,
    )


def _validate_domain_input(
    decision: DomainDowngradeInput,
    *,
    expected_domain: ModifiedGradeDomain,
) -> None:
    if decision.domain is not expected_domain:
        msg = (
            "domain input mismatch: expected "
            f"{expected_domain.value}, got {decision.domain.value}"
        )
        raise ValueError(msg)

    allowed = _ALLOWED_SEVERITIES[expected_domain]
    if decision.severity not in allowed:
        msg = (
            f"severity {decision.severity.value} is not allowed for "
            f"domain {expected_domain.value}"
        )
        raise ValueError(msg)


def _downgrade_certainty(
    current: EvidenceCertaintyLevel,
    steps: int,
) -> EvidenceCertaintyLevel:
    current_idx = _CERTAINTY_ORDER.index(current)
    next_idx = min(current_idx + steps, len(_CERTAINTY_ORDER) - 1)
    return _CERTAINTY_ORDER[next_idx]


def _build_explanation(records: list[DomainDowngradeRecord]) -> str:
    if not records:
        return "No downgrades were applied; certainty remained high."

    summary = "; ".join(
        f"{record.domain.value}: {record.severity.value} ({record.reason})" for record in records
    )
    return f"Modified GRADE downgrades applied from high certainty: {summary}."


def _stable_id(prefix: str, *parts: object) -> StableId:
    serialized = "|".join(str(part) for part in parts)
    digest = hashlib.sha1(f"{prefix}|{serialized}".encode()).hexdigest()[:16]
    return f"{prefix}.{digest}"
