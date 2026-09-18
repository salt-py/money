# Category taxonomy, nesting, and `money categories`

**Status:** Done

## Summary

Categories nest arbitrarily deep under two roots (`Discretionary` /
`Non-Discretionary`), which is what lets
[0008](0008-discretionary-income-report.md) work out what's essential vs.
optional without a second config file duplicating the category list.
`money categories` prints the whole taxonomy (plus which rules feed each
category) as real YAML, for a structure-only view that's safe to share
even though the underlying rules/categories files are personal and
gitignored.

## What shipped

- `config/categories.yaml`: `name` + `parent` (self-referential, multi-
  level). `seed_categories()` upserts rather than insert-or-ignores, so an
  edit to `parent` (re-nesting a category) actually applies on the next
  command rather than being silently skipped once a name already exists.
- `money categories [category]`: builds the tree as a nested dict and
  dumps it via `yaml.safe_dump` -- real, parseable YAML, not custom
  indented text. Each rule shows its `label` when set, falling back to
  the raw pattern only when there's no label. The optional `category`
  argument prints just that category's subtree instead of the whole tree.
- Optional `label:` field on rules -- a human-readable name for a cryptic
  pattern (a reference-number-prefixed merchant string, say), prompted for
  interactively in `money categorize`'s "save a rule?" step.
- Env-backed rules show up in the tree by their `.env` variable *name*
  only, never the real value.

## Key decisions

- **Two fixed roots, not a flat "essential" flag per category.** Nesting
  under `Discretionary`/`Non-Discretionary` means a new sub-category (e.g.
  splitting "Bills & Utilities" into "Utilities"/"Council Tax"/"Phone &
  Broadband") inherits the right bucket automatically by walking the
  parent chain, rather than needing to repeat the essential/discretionary
  choice at every level.
- **Real YAML output, not a custom tree-printer** -- this was a direct
  ask: the original hand-rolled indented-text format was harder to
  skim/diff than just emitting the structure as YAML directly.
- **Structure only, never rule content that's actually sensitive** (real
  account numbers, real balances) -- this command is explicitly called
  out as safe to run and share regardless of the "run this yourself for
  anything touching real data" rule elsewhere in the project.
