# USER GUIDE

## What this tool is for

`cosmin-assistant` is a deterministic, auditable Python package to support COSMIN-based appraisal from parsed article markdown.

It is designed to help reviewers:

- extract explicit evidence from article text spans
- keep provenance from text span to derived objects
- prepare structured inputs for later COSMIN RoB, measurement-property rating, synthesis, and modified GRADE steps

The package is built for reviewer-in-the-loop use, not fully autonomous decision-making.

## What it is not for

This tool is not:

- a black-box replacement for COSMIN-trained reviewers
- a PDF parser or OCR tool
- a system that may infer missing evidence
- a finalized end-to-end COSMIN automation pipeline (yet)

## Scientific scope and limitations

- PROM is the reference implementation.
- PBOM and activity profiles are adapted implementations and may remain partial.
- Non-PROM workflows are not assumed equivalent to PROM workflows.
- Evidence must be explicitly present in source text; no evidence may be invented.
- Ambiguous, conflicting, or missing evidence must remain explicit (for example `ambiguous`, `reviewer_required`, or `indeterminate` in later stages).
- Instrument versions and subscales must be treated as separate appraisal units.

## Current implementation status

### 1) Available now

- Typed core enums and Pydantic entities
- Profile capability system:
  - `PromProfile` (broadest coverage metadata)
  - `PbomProfile` (explicit adaptation limits)
  - `ActivityMonitorProfile` (explicit adaptation limits)
- Markdown parsing with provenance:
  - heading hierarchy
  - paragraph and sentence spans
  - stable span IDs
  - file path + heading path + character and line ranges
- Context extraction (study/instrument metadata) with:
  - raw and normalized values
  - ambiguity preservation
  - `not_reported` versus `not_detected`
  - multiple subsamples in one article
- Statistics candidate extraction with provenance for:
  - Cronbach alpha, ICC, weighted kappa, SEM, SDC, LoA, MIC
  - CFI, TLI, RMSEA, SRMR, AUC, correlations
  - DIF findings, measurement invariance findings
  - known-groups/comparator results
  - responsiveness-related statistics
- Initial COSMIN RoB infrastructure:
  - common item-assessment utilities
  - common box aggregation utilities
  - explicit worst-score-counts implementation
  - explicit `NOT_APPLICABLE` exclusion handling
- Initial modular COSMIN RoB box assessors:
  - Box 3 Structural validity
  - Box 4 Internal consistency
  - Box 6 Reliability

### 2) Provisional after Task 10

Planned but still provisional:

- expanded deterministic COSMIN RoB scoring coverage beyond Box 3/4/6
- first deterministic good-measurement-property rating pass
- explicit `reviewer_required` hooks where rules are non-deterministic

Treat any post-Task-10 behavior as provisional until validated on real papers and documented in the decision log.

### 3) Reviewer workflow after Task 13

Planned reviewer workflow (not complete yet):

- explicit reviewer checkpoints before final judgments
- persisted reviewer overrides with reasons and evidence references
- conflict-resolution handling for mixed/contradictory study evidence

### 4) Table export workflow after Task 15

Planned export workflow (not complete yet):

- COSMIN-style summary tables in markdown, CSV, and DOCX
- auditable links from table cells to evidence and scoring rules
- run-level artifacts suitable for supplementary files

## Repository structure

- `src/cosmin_assistant/models/`: typed core enums and entities
- `src/cosmin_assistant/extract/`: markdown parsing, provenance, context/statistics extraction
- `src/cosmin_assistant/profiles/`: PROM/PBOM/activity profile capability metadata
- `src/cosmin_assistant/cosmin_rob/`: RoB infrastructure + initial Box 3/4/6 modules
- `src/cosmin_assistant/measurement_rating/`: rating stage placeholder (future logic)
- `src/cosmin_assistant/synthesize/`: synthesis stage placeholder (future logic)
- `src/cosmin_assistant/grade/`: modified GRADE stage placeholder (future logic)
- `src/cosmin_assistant/tables/`: table/export stage placeholder (future logic)
- `tests/`: pytest suite with fixtures
- `docs/`: method scope and implementation docs

## Installation

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Notes:

- Python 3.11+ is required.
- Apple Silicon macOS is supported.

## Running tests

```bash
python3 -m ruff check .
python3 -m black --check .
python3 -m mypy
python3 -m pytest -q
```

## Expected input files

Current expected input is one or more parsed article markdown files (`.md`), typically one study report per file.

Recommended markdown conventions:

- use heading levels (`#`, `##`, `###`) to preserve section hierarchy
- keep paragraph text intact (avoid aggressive manual truncation)
- keep study statistics in plain text (not only images/tables outside text)

Current parser behavior:

- parses headings, paragraphs, and sentence spans
- preserves exact provenance for each span
- does not perform semantic interpretation beyond extraction candidates

## Evidence traceability principles

Every downstream judgment must be traceable through:

`article text span -> extracted evidence object -> deterministic rule -> output cell`

Current implementation already supports the first two links via stable span IDs and provenance metadata. Later tasks will complete rule and output-cell linkage.

Practical audit checks:

- every extracted context/statistic candidate has at least one evidence span ID
- every candidate retains raw source text
- normalized values never replace the raw text record
- for RoB boxes, `NOT_APPLICABLE` items are explicit and excluded from worst-score-counts

## Single-article workflow

Use the Python API now (CLI is not fully implemented yet).

```python
from pathlib import Path

from cosmin_assistant.extract import (
    extract_context_from_markdown_file,
    extract_statistics_from_markdown_file,
)

article_path = "data/article_001.md"
run_dir = Path("runs/run_001")
run_dir.mkdir(parents=True, exist_ok=True)

context = extract_context_from_markdown_file(article_path)
stats = extract_statistics_from_markdown_file(article_path)

(run_dir / "context_extraction.json").write_text(
    context.model_dump_json(indent=2),
    encoding="utf-8",
)
(run_dir / "statistics_extraction.json").write_text(
    stats.model_dump_json(indent=2),
    encoding="utf-8",
)
```

Placeholder CLI pattern for future tasks:

```bash
# Placeholder only: CLI contract may change before stabilization.
cosmin-assistant run --input data/article_001.md --profile prom --out runs/run_001/
```

Current API pattern for initial RoB box assessment:

```python
from cosmin_assistant.cosmin_rob import (
    BOX_6_ITEM_CODES,
    BoxItemInput,
    assess_box6_reliability,
)
from cosmin_assistant.models import CosminItemRating

item_inputs = tuple(
    BoxItemInput(
        item_code=item_code,
        item_rating=CosminItemRating.VERY_GOOD,
        evidence_span_ids=[f"sen.{idx+1}"],
    )
    for idx, item_code in enumerate(BOX_6_ITEM_CODES)
)

rob_bundle = assess_box6_reliability(
    study_id="study.001",
    instrument_id="inst.001",
    item_inputs=item_inputs,
)
```

## Reviewer-in-the-loop workflow

Current practical workflow:

1. Parse and extract context/statistics candidates.
2. Inspect candidate values with provenance spans.
3. Mark ambiguous/conflicting items for reviewer confirmation.
4. Keep reviewer notes external (for now) and preserve span references.

Planned workflow after Task 13:

1. deterministic draft judgments are generated
2. reviewer confirms/overrides explicitly
3. override rationale and evidence references are stored with the output artifacts

## Output files

Status as of current stage:

- available now:
  - structured extraction objects in memory
  - JSON files if you serialize model outputs manually
- not yet fully implemented:
  - the complete standard output bundle

Planned standard bundle (target state):

1. `evidence.json`
2. `rob_assessment.json`
3. `measurement_property_results.json`
4. `synthesis.json`
5. `grade.json`
6. `summary_report.md`
7. CSV exports
8. DOCX exports

Until table/export stages are implemented, treat file naming as provisional runbook conventions.

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

- collapsing multiple instrument versions into one record
- mixing subscale evidence into total-score judgments
- assuming missing text implies negative findings
- converting extracted candidate statistics directly into COSMIN pass/fail conclusions
- ignoring conflicting values reported in different sections of the same paper
- skipping provenance checks before reviewer decisions

## Current limitations

- No stable CLI workflow yet.
- COSMIN RoB coverage is initial, limited to Box 3/4/6 modules.
- Box-level ratings are deterministic from explicit item ratings; item-rating derivation from raw evidence remains limited and should be reviewer-verified.
- No completed deterministic measurement-property rating stage yet.
- No completed synthesis and modified GRADE implementation yet.
- No final table export layer yet (CSV/DOCX pipeline pending).
- Extraction is pattern-driven and may miss unusual reporting styles; reviewer verification remains required.

## Planned roadmap

- Task 8-10: expand deterministic COSMIN RoB coverage and implement first measurement-property rating passes
- Task 11-13: add synthesis logic, modified GRADE downgrading, and explicit reviewer decision lifecycle
- Task 14-15: finalize report generation and COSMIN-style table exports (markdown/CSV/DOCX)
- Post-Task 15 hardening:
  - real-paper validation across PROM/PBOM/activity profiles
  - rule documentation and calibration updates
  - reproducibility and audit refinements for publication workflows
