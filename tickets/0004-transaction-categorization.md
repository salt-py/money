# Rule-based categorization + review tool

**Status:** Done

## Summary

Every imported transaction gets a category via first-match-wins regex
rules (`config/rules.yaml`), falling back to `Uncategorized` for anything
that doesn't match. `money categorize` is the interactive loop for
clearing that backlog and saving new rules as you go.

## Profiles

[Ben](../product/ben.md), [Tom](../product/tom.md), [Elena](../product/elena.md)

- As Ben, I want an interactive, guided way to clear my Uncategorized
  backlog rather than hand-editing a YAML file, so that setting the tool
  up doesn't require understanding regex or its config format up front.
- As Tom, I want to save a rule with a friendly label the moment I
  recognize a recurring payee, so that a cryptic merchant string only
  ever needs decoding once.
- As Elena, I want my side income matched by its own rule distinct from
  my salary, so that the two are never mixed together in a report.

## What shipped

- `src/money/categorize.py`: `Rule` (pattern + category + optional
  `label`), `load_rules()`, case-insensitive first-match-wins matching
  against `"<description> <merchant>"`.
- `ENV_RULE_CATEGORIES`: rules sourced from `.env` variables rather than
  `config/rules.yaml`, for patterns built around a real identifying value
  (an account number, say) that shouldn't sit in a plain-text config file
  even a gitignored one might get pasted somewhere for debugging.
- `src/money/review.py` + `money categorize`: groups Uncategorized
  transactions by description (aggregated total, date range, which
  account(s) they're on), lets you assign a category per group, and
  optionally save a new rule (with an optional friendly `label`) so future
  imports auto-categorize the same payee.

## Key decisions

- **First-match-wins, not most-specific-match.** Simpler to reason about
  and to debug (rule order in the file *is* the precedence), at the cost
  of needing to order narrow rules before broad ones by hand. `money
  categories` (see [0005](0005-category-taxonomy-and-visualization.md))
  doubles as a way to spot an unreachable rule shadowed by an earlier
  broader one.
- **`add_rule`/`add_category` append raw text, not a full YAML
  parse+dump** -- preserves existing comments/formatting in the config
  files, which a round-trip through a YAML library would otherwise
  clobber.
- **Env-based rules always win over yaml rules** for the same reason they
  exist: a rule built on a real, identifying value is meant to be the
  more specific/authoritative one.
