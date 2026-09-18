# Foundation: local SQLite + privacy-first architecture

**Status:** Done

## Summary

The base architecture every other feature sits on: a local SQLite database,
a shared category taxonomy, an argparse CLI (`python -m money.cli ...`),
and a hard privacy boundary around anything touching real financial data.

## What shipped

- `src/money/db.py`: schema for `accounts`, `categories` (self-referential
  `parent`, for nesting), `transactions` (upserted by `external_id` so
  reimports are idempotent), `balances` (one row per import per account,
  for net-worth-over-time).
- `src/money/cli.py`: argparse entrypoint with subcommands, a shared
  `_add_cmd()` helper so every command gets both a one-line listing and
  its own `--help` page from a single description string.
- `.env` / `.gitignore` split: real credentials and data never tracked;
  `.env.example` documents required variable names with no values.

## Key decisions

- **Everything real lives in gitignored files** (`.env`, `data/`, later
  extended to `config/categories.yaml`, `config/rules.yaml`,
  `config/budget.yaml`, `config/debt.yaml` -- see
  [0010](0010-public-repo-readiness.md)). This is the operating constraint
  the whole project was built under: an AI assistant helping write this
  code should never need to see real balances, account numbers, or
  transaction content to do the work.
- **Commands that touch real data are meant to be run by the user, in
  their own terminal** -- not executed on their behalf by an assistant.
  All development and testing against this codebase uses synthetic
  fixtures instead.
- **Upsert by `external_id`, not append-only inserts** -- every importer
  (Monzo API, PDF parsing) re-running over already-imported data should be
  a no-op for unchanged rows and a category refresh for changed ones, not
  a pile of duplicates.
