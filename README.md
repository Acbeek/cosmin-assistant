# cosmin-assistant

Deterministic, auditable COSMIN appraisal assistant for parsed article markdown files.

## Scientific scope

- PROM is the reference implementation.
- PBOM and activity-monitor support are explicit adapter profiles with declared limitations.
- No evidence is invented.
- Final judgments must be traceable to source text spans.
- Missing or ambiguous evidence remains explicit (`indeterminate` / `reviewer_required`).

## Current implementation status (through Task 13)

Implemented and tested:

- Typed core enums and Pydantic models for extraction, RoB, ratings, synthesis, GRADE, and reviewer overrides.
- Profile system with explicit capability declarations:
  - `PromProfile` (fullest current metadata coverage)
  - `PbomProfile` (partial adapter)
  - `ActivityMonitorProfile` (partial adapter)
- Markdown parsing/provenance:
  - heading hierarchy + heading path tracking
  - paragraph/sentence spans with stable IDs
  - file path + line/char provenance for audit trails
- Context/statistics extraction:
  - conservative normalization with raw text retention
  - ambiguity preservation
  - `not_reported` vs `not_detected`
  - role-labeled sample sizes (enrollment/analyzed/limb-level)
  - direct/background/interpretability evidence routing
  - MIC/MCID/anchor/distribution method labels
  - responsiveness candidate detection + hypothesis-status flagging
- COSMIN RoB modules:
  - shared item utilities + box aggregation
  - worst-score-counts and explicit NA handling
  - separate modules for PROM boxes 1-10
- Study-level deterministic measurement-property ratings:
  - structural validity
  - internal consistency
  - reliability
  - cross-cultural validity / measurement invariance
  - measurement error
  - criterion validity
  - hypotheses testing for construct validity
  - responsiveness
- First-pass synthesis + modified GRADE:
  - explicit downgrade domains: risk of bias, inconsistency, imprecision, indirectness
  - inconsistent findings preserved (not force-resolved)
- Reviewer-in-the-loop flow:
  - provisional vs finalized output states
  - auditable override history and adjudication notes
  - reviewer-required item collection from extraction/RoB/rating/synthesis

Important current limitation:

- `cosmin-assess` is still a provisional orchestrator: PROM-only and currently wired to initial RoB/rating subset for end-to-end run output. Additional modules exist and are tested, but not all are yet integrated into the single-command pipeline.

## CLI usage

Run provisional assessment:

```bash
cosmin-assess article.md --profile prom --out results/run1
```

Apply reviewer overrides/adjudication and finalize:

```bash
cosmin-review results/run1 --review-file review_request.yaml --out results/run1_final --finalize
```

Minimal `review_request.yaml` shape:

```yaml
overrides:
  - target_object_type: measurement_property_result
    target_object_id: mpr.example
    field_name: computed_rating
    overridden_value: "?"
    reason: Reviewer adjudication after conflict check
    reviewer_id: reviewer.01
    evidence_span_ids: [sen.1001]
adjudication_notes:
  - decision_key: adequacy_of_hypotheses
    decision_value: confirmed
    reason: Hypotheses were predefined in protocol
    reviewer_id: reviewer.01
    evidence_span_ids: [sen.1001]
```

## Output artifacts

Assessment run outputs:

- `evidence.json`
- `rob_assessment.json`
- `measurement_property_results.json`
- `synthesis.json`
- `grade.json`
- `summary_report.md`
- `per_study_results.csv`
- `summary_report.docx` (stub exporter)
- `review_overrides.json` (initially empty)
- `adjudication_notes.json` (initially empty)
- `review_state.json` (provisional state)

Reviewed/finalized run outputs include the same files with updated review metadata and histories.

## Installation

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

If `python3.11` is unavailable on your machine, use any installed Python `>=3.11` binary.

## Development quality gates

```bash
ruff check src tests
black --check src tests
mypy src
pytest -q
```

## Package layout

- `src/cosmin_assistant/models/`
- `src/cosmin_assistant/extract/`
- `src/cosmin_assistant/profiles/`
- `src/cosmin_assistant/cosmin_rob/`
- `src/cosmin_assistant/measurement_rating/`
- `src/cosmin_assistant/synthesize/`
- `src/cosmin_assistant/grade/`
- `src/cosmin_assistant/review/`
- `src/cosmin_assistant/tables/`
- `src/cosmin_assistant/cli/`
- `src/cosmin_assistant/utils/`

See [docs/USER_GUIDE.md](docs/USER_GUIDE.md) for practical workflow guidance.
