# money

[![tests](https://github.com/salt-py/money/actions/workflows/test.yml/badge.svg)](https://github.com/salt-py/money/actions/workflows/test.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
![privacy: local-only](https://img.shields.io/badge/privacy-local--only-brightgreen.svg)

A local-only personal finance tracker: pulls transactions from Monzo via
its API, and from every other bank/card via a PDF statement parser, into a
local SQLite database, with simple CLI reports on top.

**Privacy model**: everything lives in `data/`, `.env`, `config/categories.yaml`
and `config/rules.yaml` — all gitignored, all local to your machine. No bank
credentials, account numbers, balances, or transactions are ever sent
anywhere except directly between your machine and Monzo's API.
Commands that touch real credentials or real data (`monzo-auth`,
`import-monzo`, `import-pdf`, `categorize`, `budget`, `debt`, `report`)
are meant to be run by **you**, in your own terminal — not pasted to, or
run on your behalf by, an AI assistant.

Every command has `--help` (`money --help`, `money report --help`, `money
report household --help`, etc.) with a description and a typical-flow
cheat sheet at the top level — that's the fastest way to check exact
syntax without digging through this file.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env
cp config/categories.yaml.example config/categories.yaml
cp config/rules.yaml.example config/rules.yaml
```

`categories.yaml` and `rules.yaml` are your own category taxonomy and
categorization rules — personal to your situation, so (like `.env`)
they're gitignored rather than shared. The `.example` files are just a
generic starting point; edit the copies freely (see
[Categorization](#categorization) below) as you notice mis-categorized or
`Uncategorized` transactions. Running any command without them first
gives a clear error pointing back to this step, rather than crashing.

### Monzo

1. Go to https://developers.monzo.com, log in, and create a new OAuth
   client. Set **Redirect URL** to `http://localhost:6600/monzo/callback`
   (or whatever you put in `MONZO_REDIRECT_URI`). Confidential client.
2. Copy the Client ID and Client Secret into `.env`.
3. Run:
   ```bash
   .venv/bin/python -m money.cli monzo-auth
   ```
   This opens a browser to log into Monzo. **After logging in, open the
   Monzo app on your phone and approve API access when it prompts you** —
   this is Monzo's own anti-fraud step, not something this tool controls.
4. Tokens are saved to `data/monzo_tokens.json` (gitignored) and refreshed
   automatically on future imports.

If a Monzo account comes back with no `description` from the API (seen in
practice for a shared/joint account), `import-monzo` falls back to using
its raw account id as the name — not just ugly, but a real problem, since
accounts are matched by name: without setting an override, a manual
rename would just get overwritten by a fresh duplicate account on the
next import. `MONZO_ACCOUNT_NAME_OVERRIDES` in `.env`
(`id1:Name One,id2:Name Two`) fixes both — find the id from the account's
current (ugly) name, then set e.g.
`MONZO_ACCOUNT_NAME_OVERRIDES=user_0000ABC123:Household Account`.

### Why PDF for everything else

The original plan was CSV export, with GoCardless Bank Account Data (a
free Open Banking aggregator) as an automated option for NatWest/Santander.
Neither panned out: GoCardless has closed new signups to that product (and
the other UK aggregators covering these banks require business
onboarding, not a personal signup), and NatWest's mobile app turned out to
only offer a PDF statement download, no CSV. So every non-Monzo bank goes
through `import-pdf` instead.

Four PDF layouts are supported so far, auto-detected from which keys a
bank's `config/pdf_formats/<bank>.yaml` sets — note NatWest alone needed
two different ones for its two products (current account vs. credit
card), so don't assume a bank is internally consistent either:

- **`line_types`** (NatWest current account "Transactions" export,
  confirmed against a real statement): plain whitespace-aligned text, no
  drawn table borders, one transaction per line, e.g.:
  ```
  03 Sep EXAMPLE FINANCE LTD Direct Debit -£50.00
  25 Aug ACME EXAMPLE LTD Automated Credit £2,500.00
  ```
  The transaction "Type" column's fixed vocabulary (Direct Debit, Standing
  Order, Debit Card Transaction, ...) anchors a regex that splits each line
  into date / description / type / amount. Dates have no year ("03 Sep")
  — inferred from the statement's "From ... To ..." range on page 1.

- **`table_columns`** (Santander, confirmed against a real statement): a
  real drawn table pdfplumber extracts directly, with a single unsigned
  Amount column (`flip_amount_sign: true` turns listed charges into
  negative/spend) and ordinal dates with no year ("14th Aug" — inferred
  from "Statement Date: ..." / "Previous balance as at ..." elsewhere in
  the document). Some real rows (e.g. "Interest") have no date of their
  own at all and fall back to the statement's own date.
  `skip_description_patterns` filters out non-transaction rows (opening
  balance, a "Total of New Transactions" summary line) that would
  otherwise look like real ones.

- **`date_pair: true`** (NatWest *credit card* statement — a different
  product/export than the current account's `line_types` one above,
  confirmed against a real statement): plain text again, but each real
  transaction line is anchored by *two* leading "DD MON" dates (Trans
  Date, Post Date) instead of a Type vocabulary:
  ```
  03 SEP 04 SEP EXAMPLE.COM/BILL DUBLIN IRL 9.99
  03 SEP 03 SEP DIRECT DEBIT PAYMENT 100.00 -
  ```
  A trailing "-" after the amount marks a credit/payment (stored
  positive); a bare amount is a charge (stored negative/spend). No
  skip-list needed — summary lines like "Sub-Total" don't start with two
  dates. Watch for a real quirk this format exposed: pdfplumber's text
  extraction can drop the space between a digit and the following letter
  depending on the PDF's font kerning (e.g. "03SEP" instead of "03 SEP") —
  handled, but worth knowing about if a new statement's regex mysteriously
  stops matching.

- **`positioned_columns`** (Capital One, confirmed against a real
  statement): plain text again, with two *unsigned* amount columns placed
  side by side ("Paid in" / "Paid out") rather than one signed column.
  Flattened text (what every other layout above parses) loses which
  column a given amount was actually in, so this one instead reads
  pdfplumber's word-level x-coordinates: it finds the two column header
  labels once per page, then for each transaction row checks whether the
  trailing amount sits left (credit, positive) or right (charge,
  negative/spend) of the midpoint between them.
  `skip_description_patterns` filters out a "STATEMENT TOTALS" row that —
  unusually — has both columns filled on the same row and would otherwise
  look like a real transaction.

If another bank needs a genuinely new layout beyond these four, build and
verify it the same way each of these was:

1. Save the PDF somewhere under `data/` (gitignored).
2. Dry-run it:
   ```bash
   .venv/bin/python -m money.cli import-pdf "data/some_statement.pdf" \
     --bank some_bank --account-name "Some Account" --account-type credit_card --dry-run
   ```
   This never imports anything, and its whole output is safe to paste back
   to an assistant for help: page/line/transaction counts and the detected
   statement date range only, never real transaction content.
3. If `Transactions parsed: 0`, check `statement_range` in the output — if
   it's `null`, none of the date-range label formats this app knows about
   were found (open the PDF yourself to check the actual wording — that's
   real data, so read it locally rather than pasting it here). Otherwise,
   figure out which layout it actually is (`pdfplumber`'s
   `page.extract_tables()` — with default settings and with
   `table_settings={"vertical_strategy": "text", "horizontal_strategy": "text"}`
   — is the quickest way to check for a real table) and write a
   `config/pdf_formats/<bank>.yaml` modelled on whichever of `natwest.yaml`
   / `santander.yaml` / `natwest_credit_card.yaml` / `capital_one.yaml`
   matches, or a genuinely new shape if none do.
4. Once the dry run looks right, import for real:
   ```bash
   .venv/bin/python -m money.cli import-pdf "data/some_statement.pdf" \
     --bank some_bank --account-name "Some Account" --account-type credit_card
   ```

## Day to day usage

```bash
.venv/bin/python -m money.cli import-monzo
# ... plus import-pdf for every other account whenever you have a fresh statement

.venv/bin/python -m money.cli report net-worth
.venv/bin/python -m money.cli report spending --month 2026-08
.venv/bin/python -m money.cli report household --month 2026-08
```

Import commands are safe to re-run — transactions are deduplicated (Monzo
by its own transaction IDs, PDF by a hash of date + description + amount),
so re-importing an overlapping statement period won't create duplicates.

## Budgeting

```bash
.venv/bin/python -m money.cli budget suggest --months 3 --save
.venv/bin/python -m money.cli budget show
.venv/bin/python -m money.cli report budget --month 2026-08
```

`budget suggest` averages actual spend per category over the trailing N
calendar months (default 3) and prints it as a starting point — not a
prescription, just a baseline to edit. `Credit Card Payment` is excluded
by default (it's an internal transfer paying off a card; the real spend
it represents is already counted once under whatever category the card
purchases themselves fell into — including it too would double-count).
`--save` writes the suggestion to `config/budget.yaml` (gitignored —
unlike `rules.yaml`/`categories.yaml`, this holds real derived spending
figures, not just category names/patterns). Edit that file by hand at any
time; `budget show` just prints it back.

`report budget --month YYYY-MM` compares a month's actual spend against
the saved budget, per category, showing money **out** and money **in**
separately (not netted into one number — a category with both a purchase
and a refund, or an `Uncategorized` bucket mixing real spend with
unrelated incoming transfers, would otherwise hide one side of that).
`net` (out − in) is what's compared against the budgeted amount, flagging
categories that went `OVER`. A large `Uncategorized` line here is a good
prompt to run `money categorize` again.

## Debt payoff

```bash
.venv/bin/python -m money.cli debt setup
.venv/bin/python -m money.cli debt show
.venv/bin/python -m money.cli debt plan --extra 200
```

`debt setup` is interactive. It starts from every account with a tracked
negative balance (a credit card imported via a PDF format that sets
`balance_label_pattern`, or Monzo if its live API balance ever goes
negative) and asks for APR and minimum payment per debt — neither is ever
machine-extracted from a statement, so both are always typed in by hand.
It also lets you add debts the app can't see automatically at all (an
overdraft on an account without balance tracking, e.g. NatWest current —
balance, APR, and minimum payment all entered manually). Saved to
`config/debt.yaml` (gitignored, same reasoning as `budget.yaml` — real
balances and interest rates, not just category names).

`debt plan --extra N` simulates an **avalanche** payoff: pay minimums on
everything, throw every spare pound (`N`/month, on top of minimums) at
whichever debt has the *highest effective APR* first, then roll that
payment into the next-highest once it's cleared. This is the
mathematically optimal order — it minimizes total interest paid for a
given monthly budget. Prints a payoff order with a month/date per debt,
total months to debt-free, and total interest paid. If your monthly
amount doesn't even cover the interest accruing, it says so explicitly
rather than printing a misleadingly large payoff estimate.

**Promotional rates**: if a debt is on a 0% (or reduced) intro/balance
transfer rate right now, `debt setup` asks for that separately — the
promo rate and the date it reverts to the normal APR. "Effective APR" is
the promo rate before that date, the normal rate from that date on, and
since a promo reverting can flip which debt has the highest rate partway
through, the avalanche target is recomputed every month rather than fixed
upfront (a card at 0% now but 26% once its promo ends might not be your
first priority today, but should become one later).

## Discretionary income

```bash
.venv/bin/python -m money.cli report discretionary --month 2026-08
.venv/bin/python -m money.cli report discretionary --month 2026-08 --debt-extra 200
```

Answers "after debt, bills, and household contributions, how much am I
actually free to spend?" — `income − Non-Discretionary spend − debt
minimum payments (from config/debt.yaml, plus --debt-extra if you want to
factor in a planned avalanche extra, matching `debt plan --extra`) =
available`, compared against what you actually spent under
`Discretionary` that month.

Which bucket a category falls into is `config/categories.yaml`'s
`parent:` field — every category should eventually resolve up to
`Discretionary` or `Non-Discretionary` (both are just root categories,
same taxonomy file, no separate config to keep in sync). Categories can
nest more than one level deep — e.g. `Utilities`, `Council Tax`, and
`Phone & Broadband` all have `parent: Bills & Utilities`, which itself has
`parent: Non-Discretionary` — `report discretionary` walks the whole chain,
so a category doesn't need `Discretionary`/`Non-Discretionary` as its
*direct* parent. A few are deliberately left unclassified (`parent: null`,
or a chain that dead-ends without ever reaching a root) because they're
not real spend either way — `Income` (the inflow itself), `Credit Card
Payment`/`Credit Line Payment`/`Interest` (all already modelled going
forward in `debt.yaml`, so counting them again here would double-count),
and `Transfers` (money moving between your own accounts). `Uncategorized`
is also excluded from both totals and reported separately, since it could
turn out to be either — a nonzero number there is a nudge to run `money
categorize`. When you create a new category via `money categorize`'s `n`
option, it asks which bucket it belongs in (or neither) so nothing
silently falls out of this report.

## Categorization

`config/rules.yaml` maps description/merchant text to a category, checked
top to bottom, first match wins. `config/categories.yaml` is the category
list itself, which can nest arbitrarily deep via `parent:` (see
"Discretionary income" above). Both are plain YAML — edit them freely as
you notice mis-categorized or `Uncategorized` transactions; re-running an
import will recategorize existing rows too (upsert is by external ID,
category is refreshed on every re-import).

```bash
.venv/bin/python -m money.cli categories
.venv/bin/python -m money.cli categories "Household Contribution"  # just that subtree
```

Prints the category tree as real YAML, with each category's `rules.yaml`
patterns nested underneath it as a `rules:` list (env-based rules show the
`.env` variable *name* only, never the real value, e.g. an account number)
— structure only, no financial figures, so unlike almost everything else
in this CLI it's fine for anyone (including an AI assistant) to run or see
the output of. An optional category name prints just that category and
its descendants instead of the whole tree. Also a good way to spot a rule
that's actually unreachable because an earlier, broader rule already
matches the same text first (rules are first-match-wins) — the same
pattern appearing under two different categories in this output is the
tell.

For a rule built around a real, identifying value — a specific account
number, say — put it in `.env` instead, not `rules.yaml`. Both are
gitignored, but `rules.yaml` is the kind of file you might paste
somewhere for help debugging a categorization issue; `.env` never should
be, so it's the safer home for anything you'd rather not casually expose.
`HOUSEHOLD_ACCOUNT_REF` in `.env`
(comma-separate multiple values to match any of them) builds a
`Household Contribution` rule that's checked before the yaml rules. See
`money/categorize.py`'s `ENV_RULE_CATEGORIES` for the full list of
env-backed rules this supports. After changing it, re-run whichever
`import-*` command covers that account to recategorize existing rows.

Each rule can optionally have a `label:` — a human-readable name for a
cryptic pattern (a reference-number-prefixed merchant string, say), shown
by `money categories` *instead of* the raw pattern when set (falling back
to the pattern only when there's no label). `money categorize`'s "save a
rule?" step asks for one (optional, just press Enter to skip); editing
`rules.yaml` by hand, just add a `label:` line to any entry.

### Reviewing Uncategorized transactions

```bash
.venv/bin/python -m money.cli categorize
```

Walks through every distinct `Uncategorized` description (grouped, biggest
total first — most bang for your buck triaging), showing which account(s)
it appeared on (`[NatWest Current Account]`, or a comma-separated list if
the same payee shows up on more than one account/card — often useful
context for deciding the right category). Lets you pick a category by
number (or type a new one), and can optionally save a rule to
`config/rules.yaml` so future imports auto-categorize the same payee. This
is entirely interactive and shows real transaction descriptions in your
terminal — run it yourself, don't paste its output into a chat.

## Tests

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
```

Tests run only against synthetic fixture data in `tests/fixtures/` — no
real credentials, real statements, or network calls involved.
