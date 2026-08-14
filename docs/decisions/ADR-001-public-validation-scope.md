# ADR-001: Keep public validation separate from the synthetic decision policy

- **Status:** Accepted
- **Date:** 2026-08-14

## Context

The original case study can test a contribution-margin decision policy because its
synthetic generator controls margin and cost fields. External evidence is still needed
to show that temporal SQL, modeling, calibration, and ranking work outside that
simulation. UCI Online Retail II provides licensed real transactions, but it does not
provide margin, campaign exposure, treatment cost, or causal outcomes.

## Decision

1. Add the external check inside this repository instead of creating a second, similar
   portfolio project.
2. Name the public target **180-day net revenue**, never profit or complete CLV.
3. Use DuckDB for an executable typed contract and as-of feature/label SQL.
4. Complete model selection and calibration before opening the June 2011 test snapshot.
5. Keep the fixed baseline even when it beats the model on WAPE; report ranking and point
   error together.
6. Allow the non-negative conformal correction to be zero when raw intervals already
   exceed the calibration target.
7. Publish only aggregate reports. Keep the source workbook, canonical transactions,
   snapshots, and Customer ID outputs gitignored.

## Alternatives rejected

- Claiming public revenue as contribution margin or using it to set investment ceilings.
- Tuning on the final test snapshot to manufacture a model win.
- Removing the stronger baseline or reporting only top-decile capture.
- Committing the raw workbook or row-level customer scores for convenience.

## Consequences

The repository presents a less flattering but more defensible result: the baseline wins
point accuracy, while the model improves ranking. The synthetic policy and public
validation answer different questions and retain different guardrails.
