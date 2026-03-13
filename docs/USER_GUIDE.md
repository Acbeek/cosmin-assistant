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
- a fully polished publication-template renderer with automated batch layout decisions

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
  - explicit capability metadata for:
    - review steps
    - COSMIN boxes
    - deterministic rules
    - reviewer-required decisions/questions
    - unsupported areas
    - profile-specific extraction fields
    - profile-specific table-column availability
  - safe-failure helpers for unsupported auto-scoring areas/rules
  - explicit non-PROM adaptation declaration for COSMIN steps 5-7
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
- Validation-study routing hardening:
  - target instrument under appraisal vs comparator instruments are separated
  - instrument-type classification is explicit (`prom`, `pbom`, `performance_test`, `mixed_or_unknown`)
  - a pre-rating scientific eligibility gate controls property activation status before any box/rating module runs
  - direct current-study vs background-citation statistics are separated
  - interpretability support evidence is separated from direct rating inputs
  - comparator-context evidence is separately tagged
  - Azadinia fixture regression coverage for SIGAM framing and comparator containment
  - hold-out regression coverage on unseen instrument names to check generic role/type routing behavior
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
- Structured table-builder layer:
  - Template 5 equivalent intermediate table object
  - Template 7 equivalent intermediate table object
  - Template 8 equivalent intermediate table object
  - deterministic CSV/JSON-ready conversion helpers
- DOCX table export layer:
  - Template 5/7/8 style DOCX export from intermediate table objects
  - repeated header-row flag for page breaks where feasible
  - light shading and alignment conventions (text left, numeric fields right)
  - legend/footnote paragraphs appended below tables
  - structural tests for column order, row grouping, and legend presence
- Batch-prep scaffolding (thin orchestration only):
  - directory discovery for parsed markdown files
  - per-article run orchestration using the unchanged single-paper pipeline
  - one output directory per article with normal artifacts + `run_manifest.json`
  - deterministic collision-safe output-directory naming
  - deterministic failure handling (`--continue-on-error` default, optional `--fail-fast`)
  - deterministic batch exit behavior (non-zero exit when one or more articles fail)
  - batch summary artifacts (`batch_summary.csv`, `batch_summary.json`) with run status/error columns
  - fixture-corpus metadata structure under `tests/fixtures/corpus/` for regression expansion

### 2) Provisional after Task 10

Still provisional in current CLI orchestration:

- `cosmin-assess` is PROM-only at run level.
- The single-command end-to-end run remains wired to an initial RoB/rating subset for auto-run output.
- Additional RoB and rating modules are implemented and tested, but not yet fully integrated into one unified orchestrator flow.
- Synthesis/GRADE rules are first-pass and should be calibrated on real review datasets.
- PBOM/activity profiles are deeply specified adapters but remain methodologically partial, not full PROM-equivalent pipelines.
- Batch mode is orchestration-only and intentionally does not alter scoring/routing/RoB/GRADE logic.

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

Current state:

- intermediate Template 5/7/8 table builders are available now
- reviewed-artifact table export CLI is available now (`cosmin-tables`)
- Template 5/7/8 style DOCX export is implemented
- summary report DOCX remains a separate provisional stub
- final publication-level visual polishing is still pending
- batch orchestration exists as thin per-article execution scaffold, not dashboard/caching/performance orchestration

## Repository structure

- `src/cosmin_assistant/models/`: typed core models/enums
- `src/cosmin_assistant/extract/`: parser, provenance, context/statistics extraction
- `src/cosmin_assistant/profiles/`: PROM/PBOM/activity profile adapters
- `src/cosmin_assistant/cosmin_rob/`: RoB item/box infrastructure and box modules
- `src/cosmin_assistant/measurement_rating/`: deterministic study-level rating modules
- `src/cosmin_assistant/synthesize/`: first-pass synthesis
- `src/cosmin_assistant/grade/`: modified GRADE
- `src/cosmin_assistant/review/`: override/adjudication flow
- `src/cosmin_assistant/tables/`: JSON/MD/CSV builders + Template 5/7/8 intermediate builders + Template 5/7/8 DOCX exporters + summary DOCX stub
- `src/cosmin_assistant/cli/`: assessment, review, and reviewed-table-export CLIs
- `tests/`: fixtures + regression tests
- `tests/fixtures/corpus/`: corpus manifest + per-paper expected metadata for batch/regression expansion

## Installation

```bash
python3.13 -m venv venv313
source venv313/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

If `python3.11` is not available, use any installed Python binary `>=3.11`.
The CLI now fails fast with a clear error when run under Python `<3.11`.

macOS/iCloud troubleshooting:

- If the repo is in iCloud Drive (`Mobile Documents/...`) and the environment folder is dot-prefixed (for example `.venv`), editable-install `.pth` files may be marked hidden and skipped by Python.
- Symptom: console script exists, but running `cosmin-assess` fails with `ModuleNotFoundError: No module named 'cosmin_assistant'`.
- Prefer a non-dot environment folder name such as `venv313`.
- Quick check:

```bash
python -c "import cosmin_assistant; print(cosmin_assistant.__file__)"
```

If this import works, `cosmin-assess --help` should also work.

Module fallback if your shell cannot find the console entrypoint:

```bash
PYTHONPATH=src python -m cosmin_assistant.cli.app /path/to/article.md --profile prom --out results/run1
```

Batch module fallback:

```bash
PYTHONPATH=src python -m cosmin_assistant.cli.batch_app /path/to/parsed_markdown_dir --profile prom --out results/batch_run1
```

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
- writes `run_manifest.json` to the output directory for reproducibility/audit
- prevents silent reuse of stale outputs: if the same source path is rerun into the same output directory with a changed file hash, the command fails with a clear message

## Batch workflow (Task 17b scaffold)

Run a directory batch (thin orchestration only):

```bash
cosmin-assess-batch /path/to/parsed_markdown_dir --profile prom --out results/batch_run1
```

Optional strict failure mode:

```bash
cosmin-assess-batch /path/to/parsed_markdown_dir --profile prom --out results/batch_run1 --fail-fast
```

What batch currently does:

- discovers markdown articles (recursive by default)
- executes the same single-paper pipeline once per article
- writes one output folder per article
- writes a concise batch summary with:
  - article name/path
  - detected target instrument(s)
  - study intent
  - key active properties
  - review status
- run status (`success` / `failed`)
- error message (empty for successful rows)
- if any article fails, command exit status is non-zero
- failed article directories include `batch_error.json`

What batch currently does not do:

- no scoring/routing rule changes
- no dashboard UX
- no caching/performance acceleration

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
- `run_manifest.json`
- `review_overrides.json` (empty at first)
- `adjudication_notes.json` (empty at first)
- `review_state.json` (provisional)

Generated by `cosmin-assess-batch`:

- one per-article subdirectory with the same files as `cosmin-assess`
- failed article subdirectories include `batch_error.json`
- `batch_summary.csv`
- `batch_summary.json`

Updated by `cosmin-review`:

- same artifacts with applied overrides/adjudication
- reviewed summary markdown
- non-empty override/adjudication history when used
- `review_state.json` set to finalized/provisional according to flag

Generated by `cosmin-tables` (from a reviewed/finalized output directory):

- requires `review_state.json` and finalized review status by default
- use `--allow-provisional` to explicitly permit provisional export
- default output folder: `<input-dir>/tables/` (or custom `--out-dir`)
- `template_7.json`
- `template_7.csv`
- `template_7.docx`
- `template_8.json`
- `template_8.csv`
- `template_8.docx`
- choose `--template 7`, `--template 8`, or `--template all`

Example:

```bash
find results -type f -name review_state.json
cosmin-tables --input-dir results/run1_final --out-dir results/run1_final/tables --template all
```

Provisional reviewed export (explicit opt-in):

```bash
cosmin-tables --input-dir results/run1_reviewed --out-dir results/run1_reviewed/tables --template all --allow-provisional
```

Also available through Python API:

- Template 5 equivalent table object + CSV/JSON-ready conversion
- Template 7 equivalent table object + CSV/JSON-ready conversion
- Template 8 equivalent table object + CSV/JSON-ready conversion
- Template 5 DOCX export from intermediate table object
- Template 7 DOCX export from intermediate table object
- Template 8 DOCX export from intermediate table object

Example (API-level export):

```python
from cosmin_assistant.tables import export_template7_docx

export_template7_docx(
    table=template7_table_object,
    output_path="results/template7.docx",
)
```

## Working without Codex: manual reviewer workflow

This tool is designed to be usable **without AI coding assistance**.

Codex/LLM tools can help with engineering scaffolding (metadata shells, test setup, wiring/docs), but they are **optional**. The scientific workflow must remain usable by a reviewer working manually.

### Core principle

Primary workflow:

1. draft scientific expectations manually
2. run the pipeline
3. inspect artifacts manually
4. decide whether the paper remains exploratory, is ready for protected promotion later, or reveals a narrow repair need

Do not depend on Codex to decide the science.

### Manual metadata-first intake for a new paper

Start every new paper as `exploratory` unless it has already been manually validated strongly enough to protect regressions.

#### Step 1 - read parsed markdown first

Before running anything, identify conservatively:

- likely target instrument(s) or outcomes
- likely study intent
- likely review profile (`prom` or `pbom`) and likely instrument-type context (`prom`, `pbom`, `performance_test`, `mixed_or_unknown`)
- one or two properties that should plausibly activate
- one or two properties that should remain suppressed or not applicable
- one or more must-not-happen routing/applicability errors

#### Step 2 - create metadata manually

Register the paper in `tests/fixtures/corpus/manifest.yaml` and add `tests/fixtures/corpus/<paper_id>/expected.yaml`.

Use manifest governance fields:

- `paper_id`
- `markdown_path`
- `expected_metadata_path`
- `profile`
- `protected_or_exploratory`
- `manual_validation_status`
- `evidence_pattern_class`
- `tags`

Recommended defaults:

- `protected_or_exploratory: exploratory`
- `manual_validation_status: pending_review`

In per-paper expected metadata, record stable scientific expectations only, such as:

- `expected_target_instruments`
- `expected_study_intent`
- `expected_profile_type`
- `expected_key_properties`
- `expected_key_suppressed_or_inapplicable_properties`
- `must_not_happen`

Do not pre-specify every property state or exact wording.

#### Step 3 - run single-paper pipeline first

Do not start with batch mode.

Inspect at least:

- `run_manifest.json`
- `measurement_property_results.json`
- `synthesis.json`
- `summary_report.md`

Use `rob_assessment.json` and `review_state.json` as needed for reviewer-required items and RoB context.

#### Step 4 - perform manual scientific review

Check:

1. target instrument selection
2. study intent classification
3. comparator handling
4. active properties
5. suppressed/inapplicable properties
6. cross-artifact coherence

Goal: determine whether the paper is acceptable as exploratory/protected evidence or exposes a true generic defect.

#### Step 5 - decide promotion vs repair

Keep `exploratory` when the paper is useful but not yet stable enough for strong regression assertions.

Promote to `protected` only after:

- manual artifact review
- stable target/intent behavior
- stable key-property behavior
- stable must-not-happen protection

Open a narrow repair task when a real generic defect is revealed. Do not force promotion by adjusting metadata around broken outputs.

### Where Codex can help (optional)

Codex can assist with engineering tasks such as:

- creating manifest entries
- creating expected-metadata shells
- adding integrity/regression tests
- wiring CLI/documentation changes
- generating narrow implementation plans

Codex should not replace manual scientific judgment.

### Practical rule

- **Protected**: trusted to fail loudly when core behavior regresses.
- **Exploratory**: scientifically valuable, but still too uncertain to anchor hard regression assertions.

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
- allowing comparator instruments to be scored as the target instrument under appraisal
- merging enrollment/analyzed/limb counts into one unlabeled number
- collapsing conflicting evidence into a single confident judgment
- accepting ratings without checking prerequisites and evidence IDs
- overriding derived outputs without recording adjudication reason/evidence

## Current limitations

- End-to-end CLI orchestration is still provisional and PROM-focused.
- Full module availability is ahead of full run-level integration.
- PBOM/activity profiles explicitly mark unsupported/reviewer-required areas; this is intentional and reflects conservative adaptation boundaries.
- Content validity and PROM development remain conservative reviewer-in-the-loop areas.
- Modified GRADE and synthesis are first-pass deterministic implementations.
- Template 5/7/8 DOCX exports are implemented, but publication-level styling polish is still pending.
- Batch orchestration is intentionally thin in this task (per-article runs + summary only).
- Pattern-based extraction may miss uncommon reporting styles; reviewer verification remains required.

## Planned roadmap

- integrate remaining implemented RoB/rating modules into a broader orchestrated CLI pipeline
- improve profile-aware routing for PBOM/activity adapter paths
- extend synthesis/GRADE calibration against real review datasets
- wire Template 5/7/8 builders/exporters into richer CLI flows and refine final COSMIN-style DOCX layout
- perform larger real-paper validation with documented decision-log updates
