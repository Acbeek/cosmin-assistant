# ARCHITECTURE

## High-level structure

- `src/cosmin_assistant/models/`: data model placeholders
- `src/cosmin_assistant/extract/`: extraction stage placeholders
- `src/cosmin_assistant/profiles/`: profile adapter placeholders
- `src/cosmin_assistant/cosmin_rob/`: COSMIN RoB stage placeholders
- `src/cosmin_assistant/measurement_rating/`: property rating stage placeholders
- `src/cosmin_assistant/grade/`: modified GRADE stage placeholders
- `src/cosmin_assistant/synthesize/`: synthesis stage placeholders
- `src/cosmin_assistant/tables/`: reporting/table output placeholders
- `src/cosmin_assistant/utils/`: shared utility placeholders

## Architectural policy

- Deterministic and auditable pipeline.
- Reviewer-in-the-loop for non-deterministic judgments.
- No implicit inference from missing evidence.
