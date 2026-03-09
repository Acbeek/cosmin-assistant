# USER GUIDE

## What this tool is for

`cosmin-assistant` supports COSMIN-based appraisal from parsed article markdown with deterministic, auditable processing.

It is built to help reviewers:

- extract explicit evidence only
- keep evidence-to-judgment traceability
- run structured COSMIN RoB, study-level rating, synthesis, and modified GRADE steps
- apply reviewer overrides and adjudication without changing raw evidence

## What it is not for

This tool is not:

- a replacement for COSMIN-trained reviewer judgment
- a PDF/OCR parser
- a black-box auto-rater that can infer missing evidence
- a final COSMIN table rendering system (DOCX output is still a stub interface)

## Scientific scope and limitations

- PROM is the reference implementation.
- PBOM and activity-monitor profiles are adapted and may remain partial.
- Non-PROM rules are not assumed equivalent to PROM rules.
- No evidence may be invented.
- All final judgments must be traceable to article text spans.
- Reviewer confirmation is required for non-deterministic decisions.
- Instrument versions/subscales must be handled as separate appraisal units.

## Current implementation status

### 1) Available now

- Typed enums/models for extraction, RoB, measurement ratings, synthesis, modified GRADE, and review overrides.
- Profile system with explicit capabilities and limits:
  - `PromProfile`
  - `PbomProfile`
  - `ActivityMonitorProfile`
- Markdown parsing and provenance:
  - heading hierarchy/path tracking
  - paragraph/sentence spans
  - stable span IDs
  - file path + heading path + line/char provenance
- Context extraction:
  - instrument name/version/subscale/construct
  - study design, target population, language, country
  - sample-size role separation (enrollment/analyzed/limb-level)
  - follow-up schedule
  - ambiguity preserved (`detected`/`ambiguous`/`not_reported`/`not_detected`)
- Instrument and routing hardening for longitudinal PROM outcomes:
  - stronger PROM instrument detection in methods/results/outcome contexts
  - suppression of false instrument candidates (devices/calculators/software/hospitals/references)
  - direct vs background vs interpretability evidence routing
  - MIC/MCID method labeling (anchor/distribution/reliability-support)
  - responsiveness candidate detection with hypothesis-status flagging
  - Potter fixture regression coverage
- Statistics candidate extraction (no threshold interpretation at extraction stage):
  - alpha, ICC, weighted kappa, SEM, SDC, LoA, MIC/MCID/MID
  - CFI, TLI, RMSEA, SRMR, AUC, correlations
  - DIF/invariance findings
  - known-groups/comparator findings
  - responsiveness-related candidates
- COSMIN RoB infrastructure and PROM box modules:
  - worst-score-counts aggregation
  - explicit NA handling
  - item-level and box-level outputs separated
  - modules for boxes 1 through 10
- Deterministic study-level rating modules:
  - structural validity
  - internal consistency
  - reliability
  - cross-cultural validity / measurement invariance
  - measurement error
  - criterion validity
  - hypotheses testing for construct validity
  - responsiveness
  - each rating includes rule name, inputs, threshold comparisons, evidence IDs, and explanation
- First-pass synthesis and modified GRADE:
  - preserves per-study results before summary
  - explicit inconsistency handling
  - explicit downgrade records for risk of bias, inconsistency, imprecision, and indirectness
- Reviewer-in-the-loop flow:
  - provisional/finalized state
  - override history (`previous_value`, `overridden_value`, reason, reviewer, timestamp, evidence IDs)
  - adjudication notes for reviewer-only decisions
  - pending-review item collection from extraction/RoB/rating/synthesis

### 2) Provisional after Task 10

Still provisional in current CLI orchestration:

- `cosmin-assess` is PROM-only at run level.
- The single-command end-to-end run remains wired to an initial RoB/rating subset for auto-run output.
- Additional RoB and rating modules are implemented and tested, but not yet fully integrated into one unified orchestrator flow.
- Synthesis/GRADE rules are first-pass and should be calibrated on real review datasets.

### 3) Reviewer workflow after Task 13

Now available:

- run provisional assessment
- apply structured overrides/adjudication through `cosmin-review`
- finalize reviewed outputs with auditable history

Included manual decision key support:

- target-population match
- comparator suitability
- adequacy of hypotheses
- explanation of inconsistency
- indirectness
- non-PROM adaptation decisions
- content-validity judgments

### 4) Table export workflow after Task 15

Not complete yet:

- markdown/CSV exports are available
- DOCX export remains a clean stub interface
- final COSMIN-style table templates and final DOCX layout are still pending

## Repository structure

- `src/cosmin_assistant/models/`: typed core models/enums
- `src/cosmin_assistant/extract/`: parser, provenance, context/statistics extraction
- `src/cosmin_assistant/profiles/`: PROM/PBOM/activity profile adapters
- `src/cosmin_assistant/cosmin_rob/`: RoB item/box infrastructure and box modules
- `src/cosmin_assistant/measurement_rating/`: deterministic study-level rating modules
- `src/cosmin_assistant/synthesize/`: first-pass synthesis
- `src/cosmin_assistant/grade/`: modified GRADE
- `src/cosmin_assistant/review/`: override/adjudication flow
- `src/cosmin_assistant/tables/`: JSON/MD/CSV builders + DOCX stub
- `src/cosmin_assistant/cli/`: assessment and review CLIs
- `tests/`: fixtures + regression tests

## Installation

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

If `python3.11` is not available, use any installed Python binary `>=3.11`.

## Running tests

```bash
ruff check src tests
black --check src tests
mypy src
pytest -q
```

## Expected input files

Input is parsed markdown (`.md`) from outcome-measurement study reports.

Recommended formatting:

- preserve heading hierarchy (`#`, `##`, `###`)
- keep report text intact (avoid heavy manual compression)
- keep statistical statements in text where possible

## Evidence traceability principles

Audit chain:

`article text span -> extracted evidence object -> scoring/routing rule -> output artifact cell`

Reviewer checks before accepting outputs:

- each extracted item has evidence span IDs
- raw source text is retained
- normalized values do not replace raw evidence
- RoB aggregation uses explicit worst-score-counts + NA rules
- measurement ratings expose rule name, prerequisites, thresholds, and inputs
- reviewed outputs preserve override history without mutating raw evidence

## Single-article workflow

Run provisional assessment:

```bash
cosmin-assess /path/to/article.md --profile prom --out results/run1
```

Current `cosmin-assess` behavior:

- parse -> extract -> provisional RoB subset -> provisional rating subset -> first-pass synthesis/GRADE -> export
- currently PROM-only for CLI orchestration

## Reviewer-in-the-loop workflow

1. Generate provisional output:

```bash
cosmin-assess /path/to/article.md --profile prom --out results/run1
```

2. Create review request file (YAML or JSON):

```yaml
overrides:
  - target_object_type: measurement_property_result
    target_object_id: mpr.example
    field_name: computed_rating
    overridden_value: "?"
    reason: conflicting evidence unresolved
    reviewer_id: reviewer.01
    evidence_span_ids: [sen.101]
adjudication_notes:
  - decision_key: explanation_of_inconsistency
    decision_value: subgroup_mix_explains_difference
    reason: heterogeneity across prosthesis subgroups
    reviewer_id: reviewer.01
    evidence_span_ids: [sen.101]
```

3. Apply review and finalize:

```bash
cosmin-review results/run1 --review-file review_request.yaml --out results/run1_final --finalize
```

Use `--keep-provisional` if you want a reviewed-but-not-finalized output set.

## Output files

Generated by `cosmin-assess`:

- `evidence.json`
- `rob_assessment.json`
- `measurement_property_results.json`
- `synthesis.json`
- `grade.json`
- `summary_report.md`
- `per_study_results.csv`
- `summary_report.docx` (stub)
- `review_overrides.json` (empty at first)
- `adjudication_notes.json` (empty at first)
- `review_state.json` (provisional)

Updated by `cosmin-review`:

- same artifacts with applied overrides/adjudication
- reviewed summary markdown
- non-empty override/adjudication history when used
- `review_state.json` set to finalized/provisional according to flag

## Best practices

- PROM is the reference implementation.
- PBOM and activity profiles are adapted and may remain partial.
- never trust an auto-generated judgment without evidence spans
- treat versions/subscales separately
- preserve reviewer judgment for ambiguous decisions
- do not use the tool as a black box
- validate on real papers incrementally
- commit after each runbook task milestone

## Common mistakes

- treating cited background validation studies as current-study evidence
- promoting device/system names to instrument contexts
- merging enrollment/analyzed/limb counts into one unlabeled number
- collapsing conflicting evidence into a single confident judgment
- accepting ratings without checking prerequisites and evidence IDs
- overriding derived outputs without recording adjudication reason/evidence

## Current limitations

- End-to-end CLI orchestration is still provisional and PROM-focused.
- Full module availability is ahead of full run-level integration.
- Content validity and PROM development remain conservative reviewer-in-the-loop areas.
- Modified GRADE and synthesis are first-pass deterministic implementations.
- DOCX output is not final COSMIN table-template rendering.
- Pattern-based extraction may miss uncommon reporting styles; reviewer verification remains required.

## Planned roadmap

- integrate remaining implemented RoB/rating modules into a broader orchestrated CLI pipeline
- improve profile-aware routing for PBOM/activity adapter paths
- extend synthesis/GRADE calibration against real review datasets
- implement final COSMIN-style table templates and DOCX layout
- perform larger real-paper validation with documented decision-log updates
