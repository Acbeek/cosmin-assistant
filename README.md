# cosmin-assistant

Deterministic, auditable COSMIN appraisal assistant for parsed article markdown files.

## Scientific scope

- PROM is the reference implementation.
- PBOM and activity-monitor support are explicit adapter profiles with declared limitations.
- No evidence is invented.
- Final judgments must be traceable to source text spans.
- Missing or ambiguous evidence remains explicit (`indeterminate` / `reviewer_required`).

## Current implementation status (through Task 17b)

Implemented and tested:

- Typed core enums and Pydantic models for extraction, RoB, ratings, synthesis, GRADE, and reviewer overrides.
- Profile system with explicit capability declarations:
  - `PromProfile` (fullest current metadata coverage)
  - `PbomProfile` (adapted partial adapter with explicit non-PROM limits)
  - `ActivityMonitorProfile` (adapted partial adapter with explicit non-PROM limits)
- Deepened non-PROM profile adapter metadata:
  - explicit step capability matrix (reused/adapted/reviewer_required/unsupported)
  - explicit box capability matrix
  - explicit rule capability matrix
  - profile-specific extraction fields, reviewer questions, and table-column availability
  - explicit safe-failure helpers for unsupported auto-scoring areas and unavailable rules
  - explicit adapted handling for non-PROM review steps 5-7
- Markdown parsing/provenance:
  - heading hierarchy + heading path tracking
  - paragraph/sentence spans with stable IDs
  - file path + line/char provenance for audit trails
- Context/statistics extraction:
  - conservative normalization with raw text retention
  - ambiguity preservation
  - `not_reported` vs `not_detected`
  - role-labeled sample sizes (enrollment/validation/pilot/retest/analyzed/limb-level)
  - direct/background/interpretability evidence routing
  - explicit comparator-instrument-context routing bucket
  - MIC/MCID/anchor/distribution method labels
  - responsiveness candidate detection + hypothesis-status flagging
  - target-instrument versus comparator-instrument context separation for validation studies
  - generic instrument-type classification (`prom`, `pbom`, `performance_test`, `mixed_or_unknown`)
  - pre-rating property-activation eligibility statuses (direct/comparator/indirect/interpretability/support/not-assessed/not-applicable/reviewer-required)
  - role/type decisions carry explicit text-evidence rationale fields
  - enriched study context extraction:
    - recruitment setting
    - follow-up interval
    - validation/pilot/retest sample-size fields
  - conservative not-assessed property handling (e.g., criterion validity without gold standard)
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
- Structured COSMIN-style table builders (intermediate layer):
  - Template 5 equivalent (study characteristics for other properties)
  - Template 7 equivalent (per-study + summary rows with certainty)
  - Template 8 equivalent (summary-of-findings by PROM/version/subscale)
  - CSV/JSON-ready outputs via deterministic table objects and pandas converters
- DOCX export for Template 5/7/8 style tables:
  - consumes intermediate table objects (not raw extraction objects)
  - preserves per-study rows and summary rows
  - preserves version/subscale separation and multi-study grouping
  - includes repeated header row flag, legends/footnotes, light shading, and numeric alignment
  - covered by structural tests for column order, grouping, and legend presence

Important current limitation:

- `cosmin-assess` is still a provisional orchestrator: PROM-only and currently wired to initial RoB/rating subset for end-to-end run output. Additional modules exist and are tested, but not all are yet integrated into the single-command pipeline.
- Template 5/7/8 DOCX exporters are available through Python APIs; final visual-polish parity with publication templates is still pending.
- Batch mode is currently thin orchestration only (no dashboards, caching, or performance tuning yet).
- PBOM/activity adapters are intentionally conservative and do not claim full PROM-equivalent automation.

Runtime hardening now in place:

- CLI fails fast on Python `<3.11` with a clear error.
- `python -m cosmin_assistant.cli.app ...` remains supported as module fallback.
- Every output directory now includes `run_manifest.json` with:
  - `python_version`
  - `package_version`
  - `git_commit_if_available`
  - `profile`
  - `source_article_path`
  - `source_article_hash`
  - `generated_at_utc`
- Stale-output guard: reruns to the same output folder fail if the same source path now has a different file hash.
- Golden regression coverage includes Azadinia 2025 and Potter 2025 routing/extraction assertions.
- Additional hold-out regression coverage verifies generic routing on unseen instrument names (no paper-name hardcoding path).
- Batch-prep scaffolding:
  - thin batch discovery and run orchestration (`cosmin-assess-batch`)
  - one output directory per discovered markdown article
  - per-article `run_manifest.json` via the same single-paper export path
  - deterministic collision-safe per-article output naming
  - deterministic failure isolation (continue-on-error or fail-fast) with explicit exit status
  - batch summary artifacts (`batch_summary.csv` and `batch_summary.json`) with article name, detected target instrument(s), study intent, key active properties, review status, run status, and error message
  - fixture-corpus metadata structure for regression expansion in `tests/fixtures/corpus/`

## CLI usage

Before running any CLI command, install `cosmin-assistant` in your active virtual environment:

```bash
source venv313/bin/activate
python -m pip install -e ".[dev]"
hash -r
which cosmin-assess
which cosmin-metadata
```

This install provides the console commands: `cosmin-assess`, `cosmin-assess-batch`, `cosmin-review`, `cosmin-tables`, and `cosmin-metadata`.
Use `cosmin-assess` (double `s`), not `cosmin-asses`.

Example workflow for a brand-new exploratory paper (metadata-first):

```bash
cosmin-metadata init --article NonSci_Hagberg2022.md
```

```bash
cosmin-assess NonSci_Hagberg2022.md --profile prom --out results/hagberg2022_run1
```

```bash
cosmin-review results/hagberg2022_run1 --review-file review_request.yaml --out results/hagberg2022_run1_final --finalize
```

`metadata/nonsci_hagberg2022.yaml` is the metadata/governance input for `cosmin-metadata`.
`review_request.yaml` is a separate reviewer-authored YAML/JSON bundle for `cosmin-review --review-file`; it is not the metadata YAML.

```bash
cosmin-metadata review \
  --metadata metadata/nonsci_hagberg2022.yaml \
  --run-dir results/hagberg2022_run1_final \
  --json \
  --report-out results/hagberg2022_run1_final/metadata_review_finalized.json
```

```bash
cosmin-metadata decide \
  --metadata metadata/nonsci_hagberg2022.yaml \
  --review-summary results/hagberg2022_run1_final/metadata_review_finalized.json
```

```bash
cosmin-tables --input-dir results/hagberg2022_run1_final --out-dir results/hagberg2022_run1_final/tables --template all
```

Workflow notes:

- metadata-first is the default for new papers.
- optional provisional triage is available if you want an early metadata-vs-run check before review/finalize:

```bash
cosmin-metadata review \
  --metadata metadata/nonsci_hagberg2022.yaml \
  --run-dir results/hagberg2022_run1 \
  --json \
  --report-out results/hagberg2022_run1/metadata_review_provisional.json
```

- Phase 4 governance should be based on reviewed/finalized outputs, not only provisional outputs.
- table export is downstream of scientific review/finalization; it does not determine acceptability.
- `review_state.json` provisional/finalized is runtime review state.
- metadata `corpus_tier` exploratory/protected is corpus governance state.

Run thin batch orchestration over a directory of parsed markdown files:

```bash
cosmin-assess-batch /path/to/parsed_markdown_dir --profile prom --out results/batch_run1
```

Stop batch immediately on first failing article:

```bash
cosmin-assess-batch /path/to/parsed_markdown_dir --profile prom --out results/batch_run1 --fail-fast
```

Create one metadata shell interactively (Phase 2 intake helper):

```bash
cosmin-metadata init --article /path/to/article.md --out metadata/paper.yaml --paper-id paper_id
```

Notes:

- `corpus_tier` defaults to `exploratory`.
- codebook-backed fields are selected interactively by menu number or token.
- `key_active_properties` may be represented either in ordinary measurement/synthesis outputs or in reviewer-required Box 1/Box 2 workflow lanes.
- default metadata/output naming uses canonical machine-readable identifiers (`paper_id`/article stem), not reviewer prose fields.
- explicit `--out` paths still override canonical defaults.
- output is validated and written as canonical YAML only after final confirmation.
- existing files require explicit overwrite confirmation or `--overwrite`.
- metadata YAML is for `cosmin-metadata init/review/decide`.
- `review_request.yaml` is a separate YAML/JSON review request bundle for `cosmin-review --review-file`; it is not the metadata YAML.

Minimal starter `review_request.yaml` shape:

```yaml
overrides: []
adjudication_notes: []
finalize: true
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
- `run_manifest.json`
- `review_overrides.json` (initially empty)
- `adjudication_notes.json` (initially empty)
- `review_state.json` (provisional state)

Batch run outputs (`cosmin-assess-batch`):

- one subdirectory per article containing the standard assessment artifacts above
- failed article directories include `batch_error.json`
- `batch_summary.csv`
- `batch_summary.json`

Reviewed/finalized run outputs include the same files with updated review metadata and histories.

Table exports (`cosmin-tables`) from reviewed/finalized artifacts:

- default destination: `<input-dir>/tables/` (or `--out-dir`)
- `template_6.json`
- `template_6.csv`
- `template_6.docx`
- `template_7.json`
- `template_7.csv`
- `template_7.docx`
- `template_8.json`
- `template_8.csv`
- `template_8.docx`
- selective export supported via `--template 6`, `--template 7`, `--template 8`, or `--template all`
- finalized review state required by default; use `--allow-provisional` to opt in to provisional export

Template 5/6/7/8 exporters also remain available through Python APIs.

Reviewed/finalized outputs now retain run-manifest provenance explicitly:

- `run_manifest.json` is always copied from the source output directory into the reviewed/finalized directory
- when a prefixed manifest is present (for example `<artifact_prefix>__run_manifest.json`), it is copied through as well

## Installation

```bash
python3.13 -m venv venv313
source venv313/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

If `python3.11` is unavailable on your machine, use any installed Python `>=3.11` binary.

Re-enter your environment later:

- Open a new shell, then `cd` to this repository.
- Activate the same environment you used for installation.
- For `venv`-style environments, run one of:

```bash
source venv313/bin/activate
# or, if your environment folder is named differently:
source .venv/bin/activate
```

- Leave the environment with `deactivate`.

macOS/iCloud note:

- If your repository is under iCloud Drive (`Mobile Documents/...`) and you use a dot-prefixed env name like `.venv`, editable-install `.pth` files can be treated as hidden and skipped by Python, causing `ModuleNotFoundError: No module named 'cosmin_assistant'` from console scripts.
- Prefer a non-dot venv name (for example `venv313`).
- Verify import after install:

```bash
python -c "import cosmin_assistant; print(cosmin_assistant.__file__)"
```

Module fallback usage (if console entrypoint is unavailable in your shell):

```bash
PYTHONPATH=src python -m cosmin_assistant.cli.app article.md --profile prom --out results/run1
```

Batch module fallback:

```bash
PYTHONPATH=src python -m cosmin_assistant.cli.batch_app /path/to/parsed_markdown_dir --profile prom --out results/batch_run1
```

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

## Manual workflow first

`cosmin-assistant` is usable without AI coding assistance.

You can add and validate papers manually by:

- drafting metadata first
- running the single-paper pipeline
- reviewing emitted artifacts
- promoting papers to protected only after manual scientific validation

Codex/LLM assistance is optional and should be used only as a workflow accelerator, not as a replacement for reviewer judgment.

See [docs/USER_GUIDE.md](docs/USER_GUIDE.md) for practical workflow guidance.
