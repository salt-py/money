# Roadmap

The single place to answer "what's next" — every 🔲 (proposed) feature
from a profile in `product/`, pulled together, prioritized, and tracked
through to a ticket. `tickets/` records *why* something was built once
it's done; this file tracks *whether it's worth building and when*,
before a ticket exists.

## How priority is set

Roughly: how many profiles actually need it, how much it leans on
infrastructure that already exists vs. needing something new, and how
cheap it is relative to its payoff. Re-order this freely as priorities
change — it's a working backlog, not a commitment.

## Status values

- **Proposed** — listed on a profile, not yet started.
- **Ticketed** — promoted to a `tickets/NNNN-*.md`, not yet built (that
  ticket's own Status will say `Planned`/`In progress`).
- **Done** — shipped; see the linked ticket for what/why.
- **Won't do** — considered and deliberately rejected (say why, don't
  just delete the row).

## Now

The next things worth picking up.

| Feature | Profile(s) | Why now | Status |
|---|---|---|---|
| A `money checkup`/`summary` command (net worth + this month vs. budget + Uncategorized backlog, one glance) | Marcus, Ben | Two profiles want the exact same thing for different reasons; pure composition of reports that already exist, no new data needed. | Proposed |
| Recurring-payment detection | Tom | Directly extends the existing categorization engine rather than needing new infrastructure; the underlying transaction data already supports it. | Proposed |
| `CONTRIBUTING.md` + linting in CI | Engineering | Cheap, and the repo has been public since [0010](../tickets/0010-public-repo-readiness.md) with neither in place yet. | Proposed |

## Next

Worth doing once the "Now" items are through.

| Feature | Profile(s) | Why next | Status |
|---|---|---|---|
| Named savings goals + on-pace projection | Sofia | Builds directly on `report discretionary` ([0008](../tickets/0008-discretionary-income-report.md)); mirrors the debt planner's shape (amount + date + rate of progress) so a lot of the "how do I model this" thinking is already done. | Proposed |
| Budget mid-month pacing | Priya | Extends `report budget` ([0006](../tickets/0006-budgeting.md)) rather than replacing it. | Proposed |
| Guided first-run setup (`money init`) | Ben | Lowers the barrier the whole tool has for a first-time user; more UX work than new logic. | Proposed |
| Two-sided shared-cost reconciliation | Jess & Alex | Real gap in the current one-way `Household Contribution` tracking ([0009](../tickets/0009-core-reports.md)), but needs a config/data-model decision (how to represent "the agreed split") first. | Proposed |
| Type checking (mypy) + test coverage reporting | Engineering | Highest-leverage remaining quality gap now that CI/tests/linting exist. | Proposed |

## Later

Real, but lower leverage right now — smaller audience, bigger scope, or dependent on something above landing first.

| Feature | Profile(s) | Status |
|---|---|---|
| Debt payoff milestones + "what if" comparisons | Dana | Proposed |
| Plan-vs-actual debt tracking over time | Dana | Proposed |
| Budget rollover handling + budget history | Priya | Proposed |
| Multiple concurrent savings goals with priority ordering | Sofia | Proposed |
| `report subscriptions` view + "gone quiet" flag | Tom | Proposed |
| Shared-expense categories distinct from personal spend | Jess & Alex | Proposed |
| Self-employed category group + tax-year report + accountant export | Elena | Proposed |
| Year-over-year comparison + multi-year trend view + savings-rate-over-time | Grace | Proposed |
| Stale-data (account not re-imported recently) warnings | Marcus | Proposed |
| Dependency update automation + security/dependency scan | Engineering | Proposed |
| Splitting up `cli.py` / `pdf_import.py` | Engineering | Proposed — revisit once either is actually hard to navigate, not preemptively (see [engineering.md](engineering.md)). |

## Done

Every ticket in [`tickets/`](../tickets/README.md) is done — see that
index for the full list and each one's profile(s).
