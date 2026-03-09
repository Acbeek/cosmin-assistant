# SUPPORTED_PROFILES

## Profiles

- `prom`
  - Status: reference implementation.
  - Scope: broadest deterministic coverage across COSMIN boxes and measurement-property rules.
  - Limitation: still requires reviewer decisions for non-deterministic judgments.
- `pbom`
  - Status: adapted partial profile.
  - Scope: explicit reuse/adaptation metadata for steps, boxes, rules, reviewer questions, and table columns.
  - Limitation: intentionally conservative; unsupported areas are explicit and fail safely.
- `activity_measure`
  - Status: adapted partial profile.
  - Scope: explicit reuse/adaptation metadata for sensor-domain workflows.
  - Limitation: PROM structural/internal/criterion assumptions are not auto-transferred.

## Method policy

- Non-PROM profiles do not silently inherit PROM assumptions.
- Non-PROM steps 5-7 are explicitly declared as adapted/reviewer-required.
- Unsupported auto-scoring areas are explicit in profile metadata and raise clear errors when requested.
