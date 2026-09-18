# Tickets

Lightweight planning docs for this project -- one file per logical feature,
not per commit or per bug. Used for both retrospectives (what already
shipped, and why it was built that way) and upcoming work (what's next,
still undecided, or blocked on something).

## Conventions

- **Filename**: `NNNN-short-slug.md`, numbered in the order they were
  opened (not necessarily the order they're worked). Zero-padded to 4
  digits so they sort correctly.
- **Status** (top of file): `Done`, `Planned`, `In progress`, or
  `Won't do`. Retrospective tickets for already-shipped work go straight
  to `Done`.
- **One feature per ticket.** A "feature" is a coherent piece of user-
  facing capability (e.g. "debt payoff planner"), not an individual PR,
  bug fix, or refactor -- those are implementation detail that belongs in
  commit history, not here.
- Keep the **Why** sections honest about trade-offs and rejected
  alternatives, not just what shipped -- that's the part git history
  doesn't capture on its own.
- **Profiles**: every ticket names the `product/` profile(s) it serves
  (see `product/README.md`), with the actual need stated as a user story
  ("As X, I want Y, so that Z"). A ticket with no profile that fits is a
  signal to either find the real one or question why the work is being
  done at all -- `product/engineering.md` exists specifically so
  technical-quality work still has a home here without forcing it onto
  an end-user profile it doesn't really belong to.

## Index

| # | Feature | Profile(s) | Status |
|---|---------|------------|--------|
| [0001](0001-foundation-and-privacy-model.md) | Foundation: local SQLite + privacy-first architecture | Engineering | Done |
| [0002](0002-monzo-api-import.md) | Monzo API import | Marcus | Done |
| [0003](0003-pdf-statement-import.md) | Multi-bank PDF statement import | Marcus | Done |
| [0004](0004-transaction-categorization.md) | Rule-based categorization + review tool | Ben, Tom, Elena | Done |
| [0005](0005-category-taxonomy-and-visualization.md) | Category taxonomy, nesting, and `money categories` | Ben, Engineering | Done |
| [0006](0006-budgeting.md) | Budget suggestion and tracking | Priya | Done |
| [0007](0007-debt-payoff-planner.md) | Debt avalanche payoff planner | Dana | Done |
| [0008](0008-discretionary-income-report.md) | Discretionary income report | Dana, Sofia | Done |
| [0009](0009-core-reports.md) | Core reports: net worth, spending, household | Marcus, Jess & Alex | Done |
| [0010](0010-public-repo-readiness.md) | Making the repo safe to publish and share | Engineering | Done |
