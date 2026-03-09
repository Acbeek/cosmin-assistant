# cosmin-assistant

Deterministic, auditable COSMIN appraisal assistant for parsed article markdown.

## Current status

Core foundations are implemented and tested:

- Typed core models and enums
- Profile system:
  - PROM reference profile
  - PBOM adapter profile with explicit limitations
  - Activity-monitor adapter profile with explicit limitations
- Markdown parsing and provenance:
  - heading hierarchy
  - paragraph/sentence spans
  - stable span IDs
  - exact file/line/char provenance
- Context extraction layer (study + instrument):
  - raw + normalized values
  - ambiguity preservation
  - `not_reported` vs `not_detected`
  - multiple subsamples per article
- Statistics extraction layer:
  - candidate extraction only (no threshold interpretation)
  - multiple values + subgroup-specific values
  - raw statistic text + normalized type/value + evidence span provenance
- COSMIN Risk of Bias (initial infrastructure):
  - shared item-assessment utilities
  - shared box aggregation utilities
  - explicit worst-score-counts logic
  - explicit `NOT_APPLICABLE` exclusion logic
  - modular initial box assessors:
    - Box 3 Structural validity
    - Box 4 Internal consistency
    - Box 6 Reliability
- Study-level measurement property rating (deterministic initial set):
  - separate modules for structural validity, internal consistency, and reliability
  - explicit rule names, inputs used, threshold comparisons, and explanations
  - explicit prerequisite handling with indeterminate output when prerequisites are missing
  - conflicting evidence preserved as inconsistent (not silently resolved)

## Package layout

- `src/cosmin_assistant/models/`
- `src/cosmin_assistant/extract/`
- `src/cosmin_assistant/profiles/`
- `src/cosmin_assistant/cosmin_rob/`
- `src/cosmin_assistant/measurement_rating/`
- `src/cosmin_assistant/grade/`
- `src/cosmin_assistant/synthesize/`
- `src/cosmin_assistant/tables/`
- `src/cosmin_assistant/utils/`

## Quality gates

- Lint: Ruff
- Format: Black
- Type-check: mypy
- Tests: pytest
- Hooks: pre-commit
- CI: GitHub Actions
