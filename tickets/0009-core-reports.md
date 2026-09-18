# Core reports: net worth, spending, household

**Status:** Done

## Summary

The baseline reporting commands that existed before budget/debt/
discretionary-income analysis got layered on top (see
[0006](0006-budgeting.md), [0007](0007-debt-payoff-planner.md),
[0008](0008-discretionary-income-report.md)).

## What shipped

- `src/money/reports.py`: `net_worth()`, `spending()`, `household()`.
- `report net-worth [--since DATE]`: latest balance per account and the
  total; `--since` also shows the total balance trend from that date.
- `report spending --month YYYY-MM [--by category]`: spend breakdown for
  one month.
- `report household --month YYYY-MM`: how much went to the household
  account that month, and what share of income that represents.

## Key decisions

- **`household` is a report over the `Household Contribution` category,
  not a bespoke table.** The recurring transfer to a shared/joint account
  is just spend matched by a categorization rule (payee/reference), so it
  reuses the same category/transaction machinery as everything else
  rather than needing its own data model.
