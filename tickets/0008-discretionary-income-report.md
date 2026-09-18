# Discretionary income report

**Status:** Done

## Summary

`report discretionary --month YYYY-MM` answers "after debt and bills and
household contributions, how much am I actually free to spend this
month" -- income minus Non-Discretionary spend minus debt commitment.

## Profiles

[Dana](../product/dana.md), [Sofia](../product/sofia.md)

- As Dana, I want to know what's actually left over after bills and debt
  minimums, so that I know how much extra I can honestly put toward debt
  payoff without guessing.
- As Sofia, I want a real, grounded "money actually free to save" number
  rather than a naive income-minus-everything guess, so that a savings
  goal projection is based on something true.

## What shipped

- `src/money/discretionary.py`: `resolve_bucket(category, parent_map)`
  (walks the category's parent chain up to a `Discretionary` /
  `Non-Discretionary` root, with a depth guard against an accidental
  cycle), `compute_discretionary(conn, month, debt_minimum_total,
  debt_extra)`.
- `report discretionary --month YYYY-MM [--debt-extra AMOUNT]`: income,
  minus everything under `Non-Discretionary`, minus debt commitments
  (minimums, plus an optional planned avalanche extra matching `debt plan
  --extra`) = what's actually free.

## Key decisions

- **This is what motivated restructuring `categories.yaml` into
  `Discretionary`/`Non-Discretionary` roots** (see
  [0005](0005-category-taxonomy-and-visualization.md)) -- the report
  itself is a thin wrapper; the real work was making the category tree
  answer "which bucket does this belong to" for an arbitrarily nested
  category without a second config file to keep in sync.
- **Debt commitment is a parameter, not derived from `Interest`/`Credit
  Card Payment` transaction categories.** Those categories are
  deliberately left unclassified (see
  [0004](0004-transaction-categorization.md)) specifically to avoid
  double-counting against `config/debt.yaml`'s own forward-looking
  minimum-payment modelling.
