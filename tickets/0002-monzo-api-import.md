# Monzo API import

**Status:** Done

## Summary

Monzo is the one account with a real personal-use developer API
(docs.monzo.com), so it gets a proper OAuth integration instead of PDF
scraping -- `money monzo-auth` for the one-time login, `money import-monzo`
to pull new transactions and balances on an ongoing basis.

## What shipped

- `src/money/importers/monzo.py`: OAuth authorization flow (`monzo-auth`,
  opens a browser, requires approving access in the Monzo app itself --
  Monzo's own anti-fraud step), token storage/refresh
  (`data/monzo_tokens.json`, gitignored), transaction + balance fetch,
  upsert into the shared schema.
- `MONZO_ACCOUNT_NAME_OVERRIDES` env var (`id1:Name One,id2:Name Two`) to
  rename an account whose Monzo API `description` field is blank.

## Key decisions

- **Bank aggregators (GoCardless) were the original plan for every non-
  Monzo account too**, but GoCardless had closed signups to new users by
  the time this was researched, so PDF import became the fallback for
  NatWest/Santander/Capital One -- see
  [0003](0003-pdf-statement-import.md). Monzo was unaffected since it has
  its own first-party API.
- **Account name overrides exist because of a real bug**: a shared/joint
  Monzo account came back from the API with an empty `description`, so
  `import-monzo` fell back to the raw (ugly) account id as the display
  name. Since accounts are matched by name on re-import, a manual rename
  in the DB would just get silently overwritten by a fresh duplicate
  account next import -- the override has to happen at import time, not
  after the fact.
