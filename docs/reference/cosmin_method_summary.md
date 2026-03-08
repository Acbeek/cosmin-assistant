# COSMIN method summary for this repository

## Purpose

This repository implements a reviewer-in-the-loop assistant for COSMIN-based appraisal of outcome measurement studies from parsed article markdown files.

The implementation is anchored to the COSMIN guideline for systematic reviews of PROMs, the COSMIN Risk of Bias checklist, the updated criteria for good measurement properties, the modified GRADE approach, and the COSMIN-style table templates.

## Scope used in this repository

- PROMs are the reference implementation.
- PBOMs and activity measures are supported only as explicit adapted profiles.
- Non-PROM workflows must not be treated as automatically identical to PROM workflows.
- Missing, ambiguous, or conflicting evidence must remain indeterminate or reviewer-required.

## High-level COSMIN workflow

COSMIN recommends a consecutive ten-step procedure for systematic reviews of PROMs.

### Part A. Perform the literature search

1. Formulate the aim of the review
2. Formulate eligibility criteria
3. Perform a literature search
4. Select abstracts and full-text articles

### Part B. Evaluate the measurement properties

5. Evaluate content validity
6. Evaluate internal structure
   - Structural validity
   - Internal consistency
   - Cross-cultural validity / measurement invariance
7. Evaluate the remaining measurement properties
   - Reliability
   - Measurement error
   - Criterion validity
   - Hypotheses testing for construct validity
   - Responsiveness
8. Describe interpretability and feasibility

### Part C. Select a PROM

9. Formulate recommendations
10. Report the systematic review

## Key review aim elements

The review aim should explicitly define:

1. the construct
2. the population
3. the type of instrument
4. the measurement properties of interest

These four elements should also drive eligibility criteria and extraction logic.

## Three sub-steps used in COSMIN evaluation

For each measurement property, the COSMIN evaluation follows three sub-steps:

1. Assess methodological quality of each included study using the COSMIN Risk of Bias checklist.
2. Rate the result of each study against the criteria for good measurement properties.
3. Summarize the evidence across studies and grade the quality of the evidence using a modified GRADE approach.

This repository mirrors that structure exactly.

## Important methodological principles

### Content validity comes first

Content validity is considered the most important measurement property.

If there is high-quality evidence that content validity is insufficient, the PROM should not be further considered in steps 6–8, and reviewers may proceed directly to recommendation formulation.

### Internal structure has a fixed order

COSMIN recommends evaluating:

1. structural validity
2. internal consistency
3. cross-cultural validity / measurement invariance

Structural validity or unidimensionality is a prerequisite for interpreting internal consistency.

### Versions and subscales are separate units

Each version of a PROM should be considered separately, including:

- language versions
- subgroup-specific versions
- subscales

This repository therefore treats each instrument version or subscale as a separate synthesis unit.

### Inconsistency must be explained or preserved

When study results are inconsistent:

- explore explanations such as population differences, methods, or language versions
- if an explanation is found, provide subgroup-specific ratings
- if no explanation is found, the overall rating is inconsistent (±)
- if there is not enough information, the overall rating is indeterminate (?)

### Quality of evidence is graded separately

Overall ratings for each measurement property are accompanied by a grading of the quality of the evidence.

The modified COSMIN GRADE approach uses:

- risk of bias
- inconsistency
- imprecision
- indirectness

The starting point is high-quality evidence, which is then downgraded as needed.

## Ratings used in this repository

### Study-result and synthesized property ratings

- `+` sufficient
- `-` insufficient
- `?` indeterminate
- `±` inconsistent

### Risk of Bias ratings

- `very_good`
- `adequate`
- `doubtful`
- `inadequate`

### Quality of evidence ratings

- `high`
- `moderate`
- `low`
- `very_low`

## Repository-specific implementation policy

### Deterministic scoring

All final scoring and aggregation logic must be deterministic Python.

### Evidence traceability

Every judgment must be traceable as:
article text span -> extracted evidence object -> scoring rule -> output

### Reviewer-required decisions

The system must escalate, not guess, when the review requires expert judgment, including:

- target-population fit
- comparator suitability
- subgroup explanation for inconsistency
- indirectness judgments
- non-PROM adaptation decisions
- adequacy of predefined hypotheses when these are not explicit in the paper

### Non-PROM adaptation

The COSMIN guideline was developed for PROMs but can guide non-PROM reviews, with steps 5–7 adapted.

Therefore:

- `prom` is the full reference profile
- `pbom` and `activity_monitor` are explicit adapted profiles
- unsupported auto-scoring areas must be declared explicitly in code and documentation

## Expected outputs

The package should ultimately produce:

- evidence extraction outputs
- COSMIN RoB outputs
- per-study measurement property ratings
- cross-study synthesis outputs
- modified GRADE outputs
- COSMIN-style tables
- reviewer-readable audit reports
