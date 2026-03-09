"""First-pass synthesis models and deterministic aggregation."""

from cosmin_assistant.synthesize.first_pass import synthesize_first_pass
from cosmin_assistant.synthesize.models import (
    StudySynthesisInput,
    SubgroupExplanationPlaceholder,
    SynthesisAggregateResult,
)

__all__ = [
    "StudySynthesisInput",
    "SubgroupExplanationPlaceholder",
    "SynthesisAggregateResult",
    "synthesize_first_pass",
]
