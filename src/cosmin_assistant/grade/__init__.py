"""Modified GRADE first-pass models and deterministic downgrade logic."""

from cosmin_assistant.grade.models import (
    DomainDowngradeInput,
    DomainDowngradeRecord,
    DowngradeSeverity,
    ModifiedGradeDomain,
    ModifiedGradeResult,
)
from cosmin_assistant.grade.modified_grade import (
    RULE_NAME_MODIFIED_GRADE,
    STARTING_CERTAINTY,
    apply_modified_grade,
    default_inconsistency_input,
    derive_imprecision_input,
)

__all__ = [
    "DomainDowngradeInput",
    "DomainDowngradeRecord",
    "DowngradeSeverity",
    "ModifiedGradeDomain",
    "ModifiedGradeResult",
    "RULE_NAME_MODIFIED_GRADE",
    "STARTING_CERTAINTY",
    "apply_modified_grade",
    "default_inconsistency_input",
    "derive_imprecision_input",
]
