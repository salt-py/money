# Multi-bank PDF statement import

**Status:** Done

## Summary

NatWest, Santander, and Capital One don't offer a usable API/aggregator
path (see [0002](0002-monzo-api-import.md)), so `money import-pdf` parses
their downloadable PDF statements instead. Four distinct real layouts
across three banks, each reverse-engineered against a real statement (read
with one-off explicit permission, never retained).

## What shipped

- `src/money/importers/pdf_import.py`: a dispatcher over four layout
  strategies, auto-detected from which keys a bank's
  `config/pdf_formats/<bank>.yaml` sets:
  - `line_types` (NatWest current account): plain whitespace-aligned
    text, a fixed vocabulary of transaction "Type" values anchors the
    regex split.
  - `table_columns` (Santander): a real drawn table pdfplumber extracts
    directly; ordinal dates with no year; some rows (e.g. "Interest")
    have no date of their own and fall back to the statement date.
  - `date_pair: true` (NatWest credit card): each transaction line is
    anchored by two leading dates (Trans Date, Post Date) instead of a
    Type vocabulary.
  - `positioned_columns` (Capital One): two unsigned amount columns side
    by side ("Paid in" / "Paid out"); flattened text can't tell which
    column a number was in, so this mode uses pdfplumber's word-level
    x-coordinates instead.
- `extract_closing_balance()`: pulls the statement's own closing balance
  (via a per-bank `balance_label_pattern`) into the `balances` table, so
  credit card accounts show up in `report net-worth` / `money debt`
  without needing a separate manual balance entry.
- `--dry-run`: prints only structural counts (page/line/transaction
  counts, detected date range) -- safe to paste back for debugging without
  exposing real content.
- `tests/fixtures/generate_synthetic_pdf.py`: generates fake statement
  PDFs (four generator functions, one per format) so the parser is fully
  unit-testable without ever touching real data.

## Key decisions

- **Don't assume any one PDF's quirks generalize.** Four layouts from
  three banks turned out to need four genuinely different parsing
  strategies -- e.g. font-kerning drops spaces unpredictably
  (`"03SEP"` vs `"03 SEP"`), so several regexes use `\s*` rather than
  `\s+`.
- **"Most rows wins" was the wrong table-extraction heuristic.** pdfplumber
  offers multiple table-detection strategies; picking whichever found the
  most rows initially favored a noisier strategy over the correct one.
  Fixed by trying the stricter `lines` strategy first, only falling back
  to `text` per-page if `lines` found nothing.
- **Idempotent re-imports need a synthetic external id.** PDFs don't carry
  a stable transaction id the way an API does, so each row's `external_id`
  is a SHA256 hash of its own content -- re-importing the same statement
  updates categories but never duplicates rows.
