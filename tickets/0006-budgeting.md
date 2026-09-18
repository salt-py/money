# Budget suggestion and tracking

**Status:** Done

## Summary

`money budget suggest` proposes a per-category monthly budget from
trailing actual spend; `money budget show` prints whatever's currently
saved; `report budget --month` compares a given month's actuals against
it.

## Profiles

[Priya](../product/priya.md)

- As Priya, I want a budget suggested from my own trailing spend rather
  than a generic template, so that the target is actually realistic for
  my life.
- As Priya, I want to compare a month's actual spend against my saved
  budget with money in and out shown separately, so that a refund
  doesn't quietly mask real overspending in the same category.

## What shipped

- `src/money/budget.py`: `suggest_budget()` (trailing N-month average
  spend per category, `--months` default 3), `load_budget()` /
  `save_budget()` (`config/budget.yaml`, gitignored -- real derived
  spending figures, not just category names).
- `money budget suggest [--months N] [--save]` and `money budget show`.
- `report budget --month YYYY-MM`: shows money out and money in
  *separately* per category rather than netting them, so e.g. a refund
  doesn't quietly cancel out against real spend in the same category.

## Key decisions

- **Suggest, don't auto-apply.** `suggest` prints the proposal; saving it
  to `config/budget.yaml` is an explicit `--save`, so a bad trailing
  average (a one-off large purchase skewing 3 months of data) doesn't
  silently become the new target.
- **`config/budget.yaml` is gitignored**, same treatment as real
  transaction data -- it's derived figures specific to one person's real
  spending, not category structure.
