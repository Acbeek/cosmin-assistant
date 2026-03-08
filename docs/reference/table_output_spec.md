# COSMIN table output specification for this repository

## Purpose

This file specifies the target output tables for this repository.

The outputs should align with the COSMIN-style table templates for systematic reviews of PROMs, while remaining implementation-friendly for automated generation from structured data.

## General principles

- The templates are designed to support clear and consistent reporting.
- The templates reflect the COSMIN guideline for systematic reviews of PROMs.
- They may be adapted for other types of outcome measurement instruments, but adaptations may be needed.
- Do not change the core column layout unless there is a strong documented reason.
- Rows may be added or deleted to match the number of PROMs, subscales, or studies.
- Tables should preferably fit on one page.
- If a table spans pages, repeated header rows should be used.
- Footnotes should be repeated on each page where relevant.
- Final manuscript submission should preferably use PDF to preserve formatting.

## Formatting rules

### Visual layout

- Use very light row shading.
- Avoid heavy horizontal rules.
- If rules are used, make them light gray and thin.
- Except for Templates 6 and 8, target cell margins are:
  - top: 0.1 cm
  - bottom: 0.05 cm
  - left/right: 0.15 cm
- Use alternating row shading to distinguish PROMs.
- Data should be presented to facilitate comparison between PROMs and across studies.

### Text and numbers

- Text should generally be left-aligned.
- Numbers should be right-aligned or decimal-aligned.
- Use an en dash for legibility.
- Each data point should be placed in its own cell wherever possible.
- Use manual line breaks at natural pauses rather than relying only on automatic wrapping.
- Use concise telegram style where possible.

## Structural rules

### PROM versions and subscales

- Each version or subscale of a PROM is treated as a separate PROM.
- Each version or subscale should therefore appear on its own row.
- PROMs and subscales should be grouped by outcome or construct.

### Multiple study reports

- When multiple study reports exist for a PROM, list additional studies in rows below.
- Do not place multiple citations in a single cell; use separate rows instead.

### Subsamples

- If a subsample is used for assessment of some measurement properties, represent this with sub-rows or an explicit footnote.

## Table implementation order for this repository

### Phase 1 target tables

1. Template 5 equivalent
2. Template 7 equivalent
3. Template 8 equivalent

### Phase 2 target tables

4. Template 4 equivalent
5. Template 6 equivalent
6. Template 1-3 equivalents for PROM characteristics, interpretability, and feasibility

The reason for this order is that the repository first needs to support:

- studies on measurement properties other than development/content validity
- per-study RoB and study result outputs
- summary-of-findings synthesis outputs

## Template 5 equivalent

### Purpose

Characteristics of studies on measurement properties other than PROM development and content validity.

### Minimum columns

- PROM
- Ref #
- Sample:
  - N
  - Age
  - Female (%)
- Disease characteristics:
  - Disease
  - Duration in years
  - Severity
- Instrument administration:
  - Setting
  - Country
  - Language
- Response rate (%)

### Notes

- If only a subsample is used for one property, indicate this with a sub-row or footnote.
- Separate rows may be needed for different properties when the analyzed sample differs.

## Template 7 equivalent

### Purpose

Per-study reporting of:

- risk of bias
- raw result
- rating for each study on a measurement property
- summarized result
- overall rating
- certainty of evidence

### Core structure

For each PROM or subscale:

- one block of rows for the included studies
- one summary row containing:
  - total sample size
  - certainty of evidence
  - overall rating
  - pooled or summarized result

### Typical property columns

- Structural validity
- Internal consistency
- Cross-cultural validity / measurement invariance
- Reliability
- Measurement error
- Criterion validity
- Hypotheses testing for construct validity
- Responsiveness

### Per-property subcolumns

- N
- RoB
- Rating and result

### Required footnote legend

- `+` sufficient
- `-` insufficient
- `±` inconsistent
- `?` indeterminate
- RoB abbreviations should be explained

### Additional rule

If one of the summarized ratings is not sufficient, provide an explanation.

## Template 8 equivalent

### Purpose

Summary of findings for each PROM across measurement properties.

### Structure

- Rows = measurement properties
- Columns = PROMs or PROM versions/subscales
- For each PROM:
  - overall rating
  - certainty of evidence

### Expected row groups

At minimum, support:

- Content validity
  - Relevance
  - Comprehensiveness
  - Comprehensibility
- Structural validity
- Internal consistency
- Cross-cultural validity
- Measurement invariance
- Reliability
- Measurement error
- Criterion validity
- Construct validity:
  - known groups
  - other instruments
- Responsiveness

### Visual legend

- Green = sufficient
- Red = insufficient
- Yellow = inconsistent
- Grey = indeterminate
- Darker shading = higher quality evidence
- Blank space = lack of evidence

### Alternate layout

An alternative Template 8a-style condensed layout may be implemented later, but the primary output should follow the standard Template 8 logic first.

## Template 4 equivalent

### Purpose

Characteristics of studies on PROM development and content validity.

### Minimum fields

- PROM
- Ref #
- Phase
- Patient sample characteristics
- Disease characteristics
- Input provided by patients
- Professional sample characteristics
- Professional background
- Input provided by professionals

## Template 6 equivalent

### Purpose

Results on:

- RoB and ratings for PROM development
- RoB and ratings for content validity
- reviewer ratings
- summarized ratings
- certainty of evidence
- comments

## Export policy

The package should export:

- machine-readable JSON
- reviewer-readable markdown
- CSV tables
- DOCX tables

For final manuscript use, the resulting tables should be exportable to PDF with formatting preserved.

## Repository implementation policy

- Build intermediate structured table objects first.
- Do not write directly from extraction output to DOCX.
- Keep table building separate from scoring logic.
- Preserve row-level provenance to the study and property level.
- Preserve the distinction between:
  - per-study result
  - summarized result
  - overall rating
  - certainty of evidence
