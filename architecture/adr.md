# Architecture Decision Records

## ADR-001: Local-only, single-process architecture — no server, no cloud component

**Status:** Accepted

**Context:** This is a personal finance tool handling real bank
credentials, balances, and transaction content. Any hosted/cloud component
would mean real financial data leaving the user's machine, and would put
that data in reach of whoever operates the hosting.

**Decision:** Everything runs as a local CLI (`src/money/cli.py`) against
a local SQLite file (`data/money.db`). The only network calls are direct,
user-initiated connections from the user's own machine to Monzo's API
(`src/money/importers/monzo.py`) — nothing is proxied or relayed through
any third party this project controls, because there is no such party.

**Consequences:** No web UI, no multi-device sync, no background jobs —
every import/report is a manually-run command. This also shaped how the
tool was *developed*: an AI assistant helping write this code never runs
commands that touch real credentials or real data itself (see
`tickets/0001-foundation-and-privacy-model.md`) — those are run by the
user, in their own terminal.

**Alternatives considered:** A hosted dashboard (rejected outright — the
whole point was zero third-party exposure of financial data). A local
web UI over the same SQLite file was considered implicitly out of scope;
the CLI has been sufficient so far and adding one is a reversible future
decision, not a foreclosed one.

---

## ADR-002: PDF statement parsing as the fallback for banks without a usable API

**Status:** Accepted

**Context:** Only Monzo offers a real personal-use developer API. The
original plan was GoCardless (Open Banking aggregator) for NatWest/
Santander/Capital One, but GoCardless had closed signups to new users by
the time this was built (`tickets/0002-monzo-api-import.md`).

**Decision:** For every non-Monzo account, the user downloads a PDF
statement from their bank's own app/site and runs `money import-pdf`
against it. `src/money/importers/pdf_import.py` auto-detects one of four
parsing strategies per bank, configured in `config/pdf_formats/<bank>.yaml`
(`tickets/0003-pdf-statement-import.md`).

**Consequences:** Import is manual and periodic (whenever a new statement
is available), not automatic/continuous the way the Monzo API import is.
Four distinct real-world layouts needed four distinct parsing strategies
— this is inherently more maintenance-prone than a single API contract,
and a bank changing its PDF export format would silently break parsing
until caught by a real import. Balance-in-recovery
(`extract_closing_balance`, `pdf_import.py:449`) was added specifically so
these accounts still show up in `report net-worth`/`money debt` despite
not having a continuous balance feed.

**Alternatives considered:** CSV export (some banks offer this) was
considered but PDF was chosen as the common denominator across all three
banks' actually-available exports at the time. Waiting for GoCardless
signups to reopen was rejected as blocking indefinitely on something
outside this project's control.

---

## ADR-003: First-match-wins regex categorization, not most-specific-match

**Status:** Accepted

**Context:** Every transaction needs a category assigned automatically at
import time, falling back to `Uncategorized` for manual review
(`tickets/0004-transaction-categorization.md`).

**Decision:** Rules in `config/rules.yaml` are checked in file order;
the first pattern that matches wins (`categorize()`, `categorize.py:71`).

**Consequences:** Rule *order* is the entire precedence model — a narrow
rule must be placed before a broader one that would otherwise shadow it.
`money categories` (`cli.py:129`) exists partly to make this auditable:
the same pattern-derived label appearing to match two different
categories in that output is the tell that an earlier broad rule is
shadowing a later narrow one.

**Alternatives considered:** Most-specific-match (e.g. longest pattern
wins) would remove the ordering footgun but adds real complexity for a
personal tool with a few dozen rules, and makes "why did this categorize
as X" harder to answer by inspection (specificity is not always obvious
from the pattern text). Rejected as unnecessary complexity for the actual
scale involved.

---

## ADR-004: Two fixed category roots (`Discretionary`/`Non-Discretionary`) drive discretionary-income, not a per-category flag

**Status:** Accepted

**Context:** `report discretionary` (`tickets/0008-discretionary-income-report.md`)
needs to know, for an arbitrarily-nested category, whether it counts as
essential or optional spend.

**Decision:** `config/categories.yaml` nests every spend category under
one of two roots. `resolve_bucket()` (`discretionary.py:32`) walks the
`parent` chain to find which root a category ultimately belongs to.

**Consequences:** A new sub-category automatically inherits the right
bucket from wherever it's nested, with no second field to keep in sync.
The cost is that every category *must* eventually resolve to one of the
two roots or an unclassified category with `parent: null` (Income,
Transfers, Credit Card Payment, Interest, Uncategorized) is deliberately
excluded from the discretionary calculation — see the per-category
comments in `config/categories.yaml.example`.

**Alternatives considered:** A boolean `essential: true/false` field per
category was rejected — it would need to be set correctly at every
nesting level independently, rather than being inherited structurally.

---

## ADR-005: Debt payoff uses avalanche (highest effective APR first), re-targeted monthly

**Status:** Accepted

**Context:** `money debt plan` (`tickets/0007-debt-payoff-planner.md`)
needed a payoff strategy, and at least one real debt carries a
promotional 0% period with a known end date.

**Decision:** `simulate_avalanche()` (`debt.py:118`) always directs any
extra payment at whichever debt has the highest *effective* APR *this
month* (`effective_apr()`, `debt.py:102`, which returns 0% during a
promo window and the real rate after it ends) — re-evaluated every
simulated month, not fixed once at plan start.

**Consequences:** Minimizes total interest paid, at the cost of a payoff
order that can feel less motivating than snowball (smallest-balance-first)
since a large high-APR balance may stay untouched-beyond-minimum for a
long time. Monthly re-targeting means a promo period ending mid-plan
correctly shifts the extra payment onto whatever's now more expensive —
a fixed-at-start target would keep paying down a debt that's no longer
the priority once its APR discount expires.

**Alternatives considered:** Snowball (smallest balance first) — rejected,
costs more total interest and this tool is explicitly a from-first-
principles calculator, not one optimized for psychological momentum.
Static (plan-start-only) APR targeting — rejected once the promotional-
rate case came up, since it produces a wrong answer for exactly that case.

---

## ADR-006: Personal config is gitignored like `.env`; the repo ships generic `.example` templates

**Status:** Accepted

**Context:** `config/categories.yaml` and `config/rules.yaml` were
originally git-tracked, containing real personal payee/category data.
Making the repo public required this to stop
(`tickets/0010-public-repo-readiness.md`).

**Decision:** Both files are gitignored, same treatment as `.env`,
`data/`, `config/budget.yaml`, and `config/debt.yaml`. Generic
`config/categories.yaml.example` / `config/rules.yaml.example` are
tracked instead. Commands fail with an explicit message pointing at the
`.example` file (`_require_config()`, `cli.py:36`) rather than silently
seeding an empty DB or crashing with a raw traceback when the real file
doesn't exist yet.

**Consequences:** Every command that reads categories/rules needs the
user to have copied the `.example` files first — a one-time setup step,
now documented in the README. Tests must not depend on the real,
gitignored files (a real bug this surfaced: `tests/test_pdf_import.py`
was loading `config/rules.yaml` directly, which broke test portability
for anyone else cloning the repo, on top of leaking a real merchant
reference into test code — fixed with a dedicated
`tests/fixtures/rules.yaml`).

**Alternatives considered:** Keeping categories/rules git-tracked but
scrubbed of personal content was rejected — the whole point is that a
user's real category/rule structure is personal to their situation and
shouldn't need to be laundered through a shared template every time it's
edited.

---

## ADR-007: Public release used a fresh single-commit history, not a rewrite of the original repo

**Status:** Accepted

**Context:** The original local repo had ~35 commits, with real personal
config tracked for most of its history. Gitignoring a file going forward
does not remove it from already-made commits — anyone cloning the repo
could recover it via `git log`.

**Decision:** Rather than rewriting the existing history in place (e.g.
via `git filter-repo`), the public repo was built by exporting the
current sanitized working tree (`git archive HEAD`) into a brand-new
git history with a single initial commit, verified standalone before the
original repo's `.git` was discarded entirely.

**Consequences:** All prior commit-by-commit history is gone — there's no
way to `git blame` back to when a given line was first written pre-launch.
This was an accepted trade-off given the alternative (in-place rewriting)
requires verifying no stale blob or reflog entry survives, which is easy
to get subtly wrong and hard to fully confirm.

**Alternatives considered:** `git filter-repo`/BFG-style history rewriting
— rejected as higher-risk for a repo that had never been pushed anywhere
(so there was no external history worth preserving continuity with)
and no easier to get right than starting clean.

---

## ADR-008: Imports are idempotent via upsert on a stable `external_id`

**Status:** Accepted

**Context:** Both import paths (Monzo API, PDF parsing) can be re-run
over previously-imported data — e.g. re-running `import-pdf` on the same
statement, or `import-monzo` picking up the same transaction again.

**Decision:** `transactions.external_id` is `UNIQUE`
(`db.py:39`), and `upsert_transaction()` (`db.py:111`) does an insert-or-
update rather than insert-or-ignore, so category changes still propagate
on re-import. Monzo transactions carry their own stable API id; PDF-
sourced ones don't, so `_external_id()` (`pdf_import.py:145`) derives one
by hashing bank + account + date + description + amount.

**Consequences:** Safe to re-run any import command as often as wanted —
core to the "manual, periodic" PDF workflow (ADR-002) actually being
usable day to day. The hash-based id for PDF rows means two textually-
identical transactions on the same date would collide (deduplicate into
one row) — accepted as an edge case rather than solved for, since it
hasn't come up against a real statement.

**Alternatives considered:** Insert-or-ignore (simpler) was rejected
because it would make a `config/rules.yaml` edit never actually
re-categorize already-imported rows without a full DB wipe.

---

## ADR-009: Rules built on a real identifying value live in `.env`, not `config/rules.yaml`

**Status:** Accepted

**Context:** Some categorization rules are naturally built around a real,
identifying value (an account reference number, say) rather than a
generic merchant string.

**Decision:** `ENV_RULE_CATEGORIES` (`categorize.py:25`) sources these
rules from `.env` variables instead, via `load_env_rules()`
(`categorize.py:51`), checked before `config/rules.yaml`'s own rules
(`cli.py:45`).

**Consequences:** Two rule sources instead of one, with env rules always
taking precedence. The distinction remains useful even after
`config/rules.yaml` itself became gitignored (ADR-006): `rules.yaml` is
the kind of file that might get pasted somewhere to debug a
categorization issue; `.env` never should be, so it stays the stricter
home for the more sensitive values.

**Alternatives considered:** Putting everything in `config/rules.yaml`
once it became gitignored (removing the need for two sources) — rejected;
the "never gets pasted anywhere" property of `.env` is stronger than
"gitignored," and worth keeping for the most sensitive values.
