# Findings

Evidence gathered from the actual codebase and `tickets/` (the retrospective
tickets covering how each feature came to be built the way it is) to ground
`architecture.md` and `adr.md`. This is a retrospective architecture pass —
the system already exists; this documents what's actually there, not a
proposal.

## What is this system, structurally?

A single-process Python CLI (`python -m money.cli ...`,
`src/money/cli.py`), run interactively by one person on their own machine.
There is no server, no hosted component, and no multi-user concern — see
`tickets/0001-foundation-and-privacy-model.md`. Every run either reads/
writes a local SQLite file (`data/money.db`, gitignored) or local YAML
config files, or (for the Monzo importer only) makes an outbound HTTPS
call to Monzo's own API.

## Data store

One SQLite database, schema in `src/money/db.py:15-55`:

- `accounts(id, institution, account_type, name, currency)` — one row per
  bank account/card, `UNIQUE(institution, name)`.
- `categories(name PRIMARY KEY, parent)` — self-referential, arbitrary
  nesting depth (`db.py:25-28`).
- `transactions(id, account_id, date, amount, description, merchant,
  category, source, external_id UNIQUE)` — `external_id` is what makes
  re-imports idempotent (`upsert_transaction`, `db.py:111`).
- `balances(id, account_id, snapshot_date, balance, UNIQUE(account_id,
  snapshot_date))` — one row per import-time snapshot, not a running
  ledger (`record_balance`, `db.py:151`).

`init_db()` (`db.py:66`) both creates this schema and seeds `categories`
from `config/categories.yaml` on every call (`seed_categories`, `db.py:73`
— an upsert, not insert-or-ignore, so an edit to a category's `parent`
takes effect on the next command run).

## Two import paths, chosen per bank's actual API availability

Per `tickets/0002-monzo-api-import.md` and
`tickets/0003-pdf-statement-import.md`: Monzo has a real personal-use
developer API, so it gets a proper OAuth integration
(`src/money/importers/monzo.py`). NatWest, Santander, and Capital One do
not (GoCardless, the originally-planned aggregator path for these, had
closed signups by the time this was built) — so those go through PDF
statement parsing instead (`src/money/importers/pdf_import.py`), with the
user downloading the PDF from their bank's own app/site and feeding it to
`money import-pdf` themselves.

`pdf_import.py` auto-detects one of four parsing strategies from which
keys a `config/pdf_formats/<bank>.yaml` sets (`parse_transactions`,
`pdf_import.py:471`, dispatching to one of `parse_transactions_from_lines`
/ `_from_date_pair_lines` / `_from_positioned_lines` / `_from_table` —
`pdf_import.py:262/290/320/395`). Four real bank exports needed four
genuinely different strategies — see `tickets/0003` for why (font-kerning
space-dropping, a table with no drawn borders, two unsigned amount
columns needing word-level x-coordinates to disambiguate).

Both import paths converge on the same upsert path into `transactions`/
`balances` — `import_pdf()` (`pdf_import.py:493`) for PDFs,
`run_import()` (`monzo.py:236`) for Monzo — so everything downstream
(categorization, reports) is import-source-agnostic.

## Categorization is applied at import time, not as a separate pass

`categorize()` (`src/money/categorize.py:71`) is called during both
`import_pdf()` and Monzo's `run_import()`, matching first-match-wins
regex rules against `"<description> <merchant>"`. Rules come from two
sources, concatenated with env rules first (`cli.py:45`,
`_load_all_rules`):

- `config/rules.yaml` (gitignored, personal) — pattern + category +
  optional `label`, loaded by `load_rules()` (`categorize.py:37`).
- `.env`-sourced rules (`ENV_RULE_CATEGORIES`, `categorize.py:25`,
  `load_env_rules()` at `categorize.py:51`) — for rules built on a real
  identifying value that shouldn't sit in a plain-text file at all, even a
  gitignored one.

Anything matching nothing lands in `Uncategorized`, cleared later via
`money categorize` (`cli.py:190`, backed by `src/money/review.py`'s
`list_uncategorized_groups`/`set_category_for_description`/`add_rule`) —
see `tickets/0004-transaction-categorization.md`.

## Category tree drives the discretionary-income calculation

`config/categories.yaml` nests under two fixed roots, `Discretionary` and
`Non-Discretionary` (`tickets/0005-category-taxonomy-and-visualization.md`).
`resolve_bucket()` (`src/money/discretionary.py:32`) walks a category's
`parent` chain up to one of those roots (depth-guarded against a cycle),
and `compute_discretionary()` (`discretionary.py:67`) uses that to compute
income minus all Non-Discretionary spend minus debt commitment — see
`tickets/0008-discretionary-income-report.md`. This is the one place the
category tree's shape is load-bearing for a calculation, rather than just
an organizational label.

## Budget and debt are their own gitignored config, read at report time

- `config/budget.yaml`: `suggest_budget()` (`src/money/budget.py:36`)
  computes a trailing-average suggestion from real transaction history;
  `save_budget()`/`load_budget()` (`budget.py:81/88`) persist/read it.
  `report budget --month` (`reports.py:110`, `budget_vs_actual`) compares
  actual vs. saved, showing money in/out separately rather than netted.
- `config/debt.yaml`: `load_debts()`/`save_debts()`
  (`src/money/debt.py:60/67`). `effective_apr()` (`debt.py:102`) accounts
  for a promotional 0% period with an end date. `simulate_avalanche()`
  (`debt.py:118`) runs a month-by-month simulation, re-targeting the
  highest *effective* APR every month (not fixed at plan start) — see
  `tickets/0007-debt-payoff-planner.md`.

Both files are gitignored, same treatment as `.env` and `data/` — real
derived financial figures, not category/rule structure.

## Everything real is local; the repo itself had to be made safe to publish

`tickets/0010-public-repo-readiness.md` documents a substantial retrofit:
`config/categories.yaml`/`rules.yaml` moved from git-tracked to gitignored
(with `.example` templates for a fresh clone), several "illustrative"
doc/test values turned out to be real figures left over from development
and were scrubbed, and the public repo was built as a fresh single-commit
history rather than attempting to rewrite ~35 commits of history that had
real personal config tracked for most of its life. This is a structural
property of the system worth diagramming: the boundary between what's
local-only (gitignored) and what's shipped (tracked, generic) is not
incidental — it's the main architectural constraint the whole project
operates under (`tickets/0001`).
