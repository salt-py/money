"""PDF statement importer, for banks whose app only offers a PDF statement
download rather than a CSV export (NatWest current account, NatWest credit
card, Santander, and Capital One so far -- four different real layouts
from three banks, so don't assume any pattern generalizes without
checking).

Four layouts are supported, auto-detected from which keys a bank's
config/pdf_formats/<bank>.yaml sets:

- `line_types` (NatWest current account "Transactions" export): plain
  whitespace-aligned text, no drawn table -- one transaction per line,
  shaped like:
      03 Sep EXAMPLE FINANCE LTD Direct Debit -£50.00
  A small fixed vocabulary of transaction "Type" values (Direct Debit,
  Standing Order, ...) anchors a regex that splits each line into date /
  description / type / amount. The amount already carries its own sign.
  Lines give day + month only ("03 Sep") -- year is inferred from the
  statement's overall date range (see `_infer_statement_range`).

- `table_columns` (Santander): a real drawn table pdfplumber can extract
  directly, with a single unsigned Amount column (so `flip_amount_sign`
  turns listed charges into negative/spend) and ordinal dates with no year
  ("14th Aug"). Some real transaction rows (e.g. "Interest") have no date
  of their own at all -- those fall back to the statement's own date.
  `skip_description_patterns` filters out non-transaction rows (opening
  balance carried forward, a "Total of New Transactions" summary line)
  that would otherwise look like real rows.

- `date_pair: true` (NatWest credit card statement): plain text again, but
  anchored differently -- each real transaction line starts with *two*
  dates (Trans Date, Post Date), not a Type vocabulary:
      03 SEP 04 SEP 12345678 EXAMPLE.COM/BILL DUBLIN IRL 9.99
      03 SEP 03 SEP DIRECT DEBIT PAYMENT 100.00 -
  A trailing " -" after the amount marks a credit/payment (stored
  positive); a bare amount is a charge (stored negative/spend). This
  two-leading-dates shape is itself specific enough that no explicit skip
  list is needed -- summary lines ("Sub-Total", "NEW BALANCE", a wrapped
  foreign-exchange continuation line) simply don't start with two dates.

- `positioned_columns` (Capital One): plain text with two *unsigned*
  amount columns side by side ("Paid in" / "Paid out") -- flattened text
  alone can't tell which column a given amount was actually in, so this
  mode uses pdfplumber's word-level x-coordinates instead of plain text
  lines: it locates the two column header labels once per page, then for
  each transaction row checks whether that row's trailing amount sits to
  the left (credit, stored positive) or right (charge, stored negative) of
  the midpoint between them. `skip_description_patterns` filters out a
  "STATEMENT TOTALS" row that (unusually) has both columns filled at once
  and would otherwise look like a real transaction.

A `--dry-run` CLI flag (see cli.py) reports only counts (pages, lines,
detected statement date range, transactions parsed) -- never real
transaction content -- so format mismatches can be debugged without
exposing real data.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path
from sqlite3 import Connection

import pdfplumber
import yaml

from money.categorize import Rule, categorize
from money.db import get_or_create_account, record_balance, upsert_transaction

MONTH_ABBR = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"],
        start=1,
    )
}

# Matches a UK-style dd/mm/yyyy date, e.g. in a "From ... To ..." header.
_FULL_DATE_RE = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")

# Matches "Statement Date: 11th September 2026" / "Account summary as at:
# 11th September 2026" style labels -- the end of a statement's coverage,
# and (for table layouts) the fallback date for a real transaction row that
# has no date of its own (e.g. an interest charge).
_STATEMENT_DATE_LABEL_RE = re.compile(
    r"(?:Statement Date|Account summary as at)\s*:?\s*"
    r"(\d{1,2})(?:st|nd|rd|th)\s+([A-Za-z]+)\s+(\d{4})",
    re.IGNORECASE,
)
# Matches "Previous balance as at 13th August 2026" -- the start of a
# statement's coverage, when present.
_PREVIOUS_BALANCE_DATE_LABEL_RE = re.compile(
    r"Previous balance as at\s+(\d{1,2})(?:st|nd|rd|th)\s+([A-Za-z]+)\s+(\d{4})",
    re.IGNORECASE,
)
# A table cell holding just an ordinal day + month, no year, e.g. "14th Aug".
_ORDINAL_CELL_RE = re.compile(r"^(\d{1,2})(?:st|nd|rd|th)\s+([A-Za-z]+)$")

# Matches "10 August - 09 September 2026" -- a statement period given as a
# single line, one shared year applying to both ends. Day/month spacing is
# `\s*` (not `\s+`) because pdfplumber's text extraction sometimes drops
# the space between adjacent words depending on the PDF's font kerning
# (seen for real as "10August -09September 2026").
_MONTH_RANGE_RE = re.compile(
    r"(\d{1,2})\s*([A-Za-z]+)\s*-\s*(\d{1,2})\s*([A-Za-z]+)\s+(\d{4})"
)

# A transaction line starting with two "DD MON" dates (Trans Date, Post
# Date), no year, e.g. "03 SEP 04 SEP EXAMPLE.COM/BILL DUBLIN IRL 9.99".
# Trans Date (the first one -- when the purchase actually happened) is the
# one kept; Post Date is only for the bank's own processing. Day/month
# spacing is `\s*` (not `\s+`) because pdfplumber's text extraction can
# drop the space between a digit and the following letter depending on
# font kerning (seen for real as "03SEP", not "03 SEP").
_DATE_PAIR_LINE_RE = re.compile(
    r"^(?P<date>\d{1,2}\s*[A-Za-z]{3}) \d{1,2}\s*[A-Za-z]{3}\s+"
    r"(?P<description>.+?)\s+"
    r"(?P<amount>[\d,]+\.\d{2})\s*(?P<credit>-)?$"
)

# Matches "Statement date 10 September 26" -- a two-digit year, single date
# (no explicit period start). "20" is prefixed to the year on the
# reasonable assumption this app is never used against a 1900s statement.
_STATEMENT_DATE_2DIGIT_YEAR_RE = re.compile(
    r"Statement date\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{2})\b", re.IGNORECASE
)

# A bare "123.45" or "1,234.56" amount word, used to identify a transaction
# row's trailing amount from word-level (not line-level) extraction.
_AMOUNT_WORD_RE = re.compile(r"^[\d,]+\.\d{2}$")


def load_pdf_format(bank: str, formats_dir: Path) -> dict:
    path = formats_dir / f"{bank}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"No PDF format config for '{bank}' at {path}. "
            f"Add one modelled on config/pdf_formats/natwest.yaml (plain-text "
            f"statement) or config/pdf_formats/santander.yaml (drawn table)."
        )
    return yaml.safe_load(path.read_text())


def _external_id(bank: str, account_name: str, date_str: str, description: str, amount: float) -> str:
    raw = f"pdf|{bank}|{account_name}|{date_str}|{description}|{amount:.2f}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _extract_pages_text(pdf_path: Path) -> list[str]:
    with pdfplumber.open(pdf_path) as pdf:
        return [page.extract_text() or "" for page in pdf.pages]


def _month_number(name: str) -> int | None:
    return MONTH_ABBR.get(name[:3].lower())


def _parse_ordinal_date(day: str, month_name: str, year: str) -> date | None:
    month = _month_number(month_name)
    if month is None:
        return None
    try:
        return date(int(year), month, int(day))
    except ValueError:
        return None


def _infer_statement_range(full_text: str) -> tuple[date, date] | None:
    """Finds the statement's overall date range, trying a couple of label
    formats banks use, searched across the whole document (some banks put
    the relevant label on a later page, not page 1). Used both to resolve
    dates that only give a day + month (no year), and as the fallback date
    for a real transaction that has no date of its own at all.
    """
    numeric = _FULL_DATE_RE.findall(full_text)
    if len(numeric) >= 2:
        d1 = date(int(numeric[0][2]), int(numeric[0][1]), int(numeric[0][0]))
        d2 = date(int(numeric[1][2]), int(numeric[1][1]), int(numeric[1][0]))
        return (d1, d2) if d1 <= d2 else (d2, d1)

    end_match = _STATEMENT_DATE_LABEL_RE.search(full_text)
    if end_match:
        end_date = _parse_ordinal_date(*end_match.groups())
        if end_date:
            start_match = _PREVIOUS_BALANCE_DATE_LABEL_RE.search(full_text)
            start_date = _parse_ordinal_date(*start_match.groups()) if start_match else None
            if not start_date:
                return (end_date, end_date)
            return (start_date, end_date) if start_date <= end_date else (end_date, start_date)

    range_match = _MONTH_RANGE_RE.search(full_text)
    if range_match:
        d1, mon1, d2, mon2, year = range_match.groups()
        month1, month2 = _month_number(mon1), _month_number(mon2)
        if month1 is not None and month2 is not None:
            year2 = int(year)
            year1 = year2 if month1 <= month2 else year2 - 1
            try:
                start = date(year1, month1, int(d1))
                end = date(year2, month2, int(d2))
                return (start, end) if start <= end else (end, start)
            except ValueError:
                pass

    two_digit_match = _STATEMENT_DATE_2DIGIT_YEAR_RE.search(full_text)
    if two_digit_match:
        end_date = _parse_ordinal_date(
            two_digit_match.group(1), two_digit_match.group(2), f"20{two_digit_match.group(3)}"
        )
        if end_date:
            return (end_date, end_date)

    return None


def _resolve_day_month(day: int, month_name: str, statement_range: tuple[date, date]) -> str | None:
    """A date with no year, e.g. "03 Sep" or "14th Aug" -- infer the year
    from whichever of the statement's start/end years places the date
    inside the statement's actual coverage range (handles a statement that
    spans a year boundary).
    """
    month = _month_number(month_name)
    if month is None:
        return None
    start, end = statement_range
    candidates = []
    for year in {start.year, end.year}:
        try:
            candidates.append(date(year, month, day))
        except ValueError:
            continue
    in_range = [c for c in candidates if start <= c <= end]
    chosen = in_range[0] if in_range else (candidates[0] if candidates else None)
    return chosen.strftime("%Y-%m-%d") if chosen else None


_DAY_MONTH_RE = re.compile(r"^(\d{1,2})\s*([A-Za-z]{3,})$")


def _split_day_month(cell: str) -> tuple[str, str] | None:
    """Splits a "DD Mon" (or jammed-together "DDMon") cell into day and
    month parts. pdfplumber's text extraction can drop the space between a
    digit and the following letter depending on a PDF's font kerning
    (confirmed for real: "03SEP", not "03 SEP", on a NatWest credit card
    statement) -- `str.split()` alone would fail on that.
    """
    m = _DAY_MONTH_RE.match(cell.strip())
    return (m.group(1), m.group(2)) if m else None


def _build_line_pattern(line_types: list[str]) -> re.Pattern:
    types_alternation = "|".join(re.escape(t) for t in line_types)
    return re.compile(
        rf"^(?P<date>\d{{1,2}} [A-Za-z]{{3}})\s+"
        rf"(?P<description>.+?)\s+"
        rf"(?P<type>{types_alternation})\s+"
        rf"(?P<amount>-?£[\d,]+\.\d{{2}})\s*$"
    )


def parse_transactions_from_lines(pdf_path: Path, fmt: dict) -> list[dict]:
    """Fallback for statement PDFs with no drawn table at all -- just
    whitespace-aligned text, one transaction per line. See module docstring.
    """
    pages_text = _extract_pages_text(pdf_path)
    statement_range = _infer_statement_range("\n".join(pages_text))
    if not statement_range:
        return []

    pattern = _build_line_pattern(fmt["line_types"])
    transactions = []
    for page_text in pages_text:
        for line in page_text.splitlines():
            m = pattern.match(line.strip())
            if not m:
                continue
            day_month = _split_day_month(m.group("date"))
            if not day_month:
                continue
            date_iso = _resolve_day_month(int(day_month[0]), day_month[1], statement_range)
            if not date_iso:
                continue
            amount = float(m.group("amount").replace("£", "").replace(",", ""))
            description = m.group("description").strip()
            transactions.append({"date": date_iso, "description": description, "amount": amount})
    return transactions


def parse_transactions_from_date_pair_lines(pdf_path: Path, fmt: dict) -> list[dict]:
    """For statement PDFs shaped like a NatWest credit card statement: plain
    text, each real transaction line anchored by two leading "DD MON"
    dates rather than a Type vocabulary. See module docstring.
    """
    pages_text = _extract_pages_text(pdf_path)
    statement_range = _infer_statement_range("\n".join(pages_text))
    if not statement_range:
        return []

    transactions = []
    for page_text in pages_text:
        for line in page_text.splitlines():
            m = _DATE_PAIR_LINE_RE.match(line.strip())
            if not m:
                continue
            day_month = _split_day_month(m.group("date"))
            if not day_month:
                continue
            date_iso = _resolve_day_month(int(day_month[0]), day_month[1], statement_range)
            if not date_iso:
                continue
            amount = float(m.group("amount").replace(",", ""))
            if not m.group("credit"):
                amount = -amount  # a bare amount is a charge -> spend
            description = m.group("description").strip()
            transactions.append({"date": date_iso, "description": description, "amount": amount})
    return transactions


def parse_transactions_from_positioned_lines(pdf_path: Path, fmt: dict) -> list[dict]:
    """For statement PDFs like Capital One's: plain text with two unsigned
    amount columns side by side ("Paid in" / "Paid out"). Flattened text
    loses which column an amount was in, so this reads pdfplumber's
    word-level x-coordinates directly instead of `page.extract_text()`.
    See module docstring.
    """
    cfg = fmt["positioned_columns"]
    header_anchor = cfg["header_anchor"].lower()
    credit_label = cfg["credit_column_label"].lower()
    debit_label = cfg["debit_column_label"].lower()
    skip_patterns = [re.compile(p, re.IGNORECASE) for p in fmt.get("skip_description_patterns", [])]

    pages_text = _extract_pages_text(pdf_path)
    statement_range = _infer_statement_range("\n".join(pages_text))
    if not statement_range:
        return []

    transactions = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            if not words:
                continue

            rows: dict[float, list[dict]] = {}
            for w in words:
                rows.setdefault(round(w["top"], 1), []).append(w)
            for top in rows:
                rows[top].sort(key=lambda w: w["x0"])

            # Locate this page's column header (repeated per page) and the
            # x-position boundary between its two amount columns.
            credit_x = debit_x = header_top = None
            for top in sorted(rows):
                row_text = " ".join(w["text"] for w in rows[top]).lower()
                if header_anchor not in row_text:
                    continue
                for w in rows[top]:
                    if w["text"].lower() == credit_label:
                        credit_x = w["x0"]
                    if w["text"].lower() == debit_label:
                        debit_x = w["x0"]
                header_top = top
                break
            if credit_x is None or debit_x is None:
                continue  # no transactions table on this page
            boundary = (credit_x + debit_x) / 2

            for top in sorted(rows):
                if header_top is not None and top <= header_top:
                    continue
                row = rows[top]
                if len(row) < 3:
                    continue
                last = row[-1]
                if not _AMOUNT_WORD_RE.match(last["text"]):
                    continue
                day_month = _split_day_month(f"{row[0]['text']} {row[1]['text']}")
                if not day_month:
                    continue
                description = " ".join(w["text"] for w in row[2:-1]).strip()
                if not description or any(p.search(description) for p in skip_patterns):
                    continue
                date_iso = _resolve_day_month(int(day_month[0]), day_month[1], statement_range)
                if not date_iso:
                    continue
                amount = float(last["text"].replace(",", ""))
                if last["x0"] >= boundary:
                    amount = -amount  # right-hand ("paid out") column -> spend

                transactions.append({"date": date_iso, "description": description, "amount": amount})
    return transactions


def parse_transactions_from_table(pdf_path: Path, fmt: dict) -> list[dict]:
    """For statement PDFs with a real drawn table (pdfplumber's default
    table extraction finds it directly). See module docstring.
    """
    cols = fmt["table_columns"]
    date_col, desc_col, amount_col = cols["date"].lower(), cols["description"].lower(), cols["amount"].lower()
    skip_patterns = [re.compile(p, re.IGNORECASE) for p in fmt.get("skip_description_patterns", [])]
    flip = fmt.get("flip_amount_sign", False)

    with pdfplumber.open(pdf_path) as pdf:
        pages = list(pdf.pages)
        full_text = "\n".join(page.extract_text() or "" for page in pages)
        statement_range = _infer_statement_range(full_text)
        if not statement_range:
            return []
        fallback_date = statement_range[1].strftime("%Y-%m-%d")

        transactions = []
        for page in pages:
            for table in page.extract_tables():
                if not table or len(table) < 2:
                    continue
                header = [(c or "").strip().lower() for c in table[0]]
                if date_col not in header or desc_col not in header or amount_col not in header:
                    continue  # not the transactions table
                date_i, desc_i, amount_i = header.index(date_col), header.index(desc_col), header.index(amount_col)

                for row in table[1:]:
                    if desc_i >= len(row) or amount_i >= len(row):
                        continue
                    description = (row[desc_i] or "").strip().replace("\n", " ")
                    if not description or any(p.search(description) for p in skip_patterns):
                        continue
                    amount_raw = (row[amount_i] or "").strip()
                    if not amount_raw:
                        continue
                    try:
                        amount = float(amount_raw.replace(",", "").replace("£", ""))
                    except ValueError:
                        continue
                    if flip:
                        amount = -amount

                    date_raw = (row[date_i] or "").strip() if date_i < len(row) else ""
                    date_iso = None
                    m = _ORDINAL_CELL_RE.match(date_raw) if date_raw else None
                    if m:
                        date_iso = _resolve_day_month(int(m.group(1)), m.group(2), statement_range)
                    date_iso = date_iso or fallback_date

                    transactions.append({"date": date_iso, "description": description, "amount": amount})
    return transactions


def extract_closing_balance(pdf_path: Path, fmt: dict) -> float | None:
    """Pulls the statement's closing balance via `balance_label_pattern`
    (a regex with one capture group for the amount), if the format config
    sets one. Used to keep the `balances` table populated for credit card
    accounts too -- unlike Monzo, which gets its balance from the API
    directly, a PDF-imported account otherwise never gets a balance
    snapshot at all (only transactions), which would make it invisible to
    `report net-worth` and to any debt payoff planning.
    """
    pattern = fmt.get("balance_label_pattern")
    if not pattern:
        return None
    full_text = "\n".join(_extract_pages_text(pdf_path))
    m = re.search(pattern, full_text, re.IGNORECASE)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except (ValueError, IndexError):
        return None


def parse_transactions(pdf_path: Path, fmt: dict) -> list[dict]:
    """Returns normalized transaction dicts. Rows/lines that don't look
    like a real transaction are silently skipped -- the simplest reliable
    way to filter out headers, footers, and summary rows.
    """
    if "line_types" in fmt:
        return parse_transactions_from_lines(pdf_path, fmt)
    if "table_columns" in fmt:
        return parse_transactions_from_table(pdf_path, fmt)
    if fmt.get("date_pair"):
        return parse_transactions_from_date_pair_lines(pdf_path, fmt)
    if "positioned_columns" in fmt:
        return parse_transactions_from_positioned_lines(pdf_path, fmt)
    raise ValueError(
        "PDF format config must set 'line_types' (Type-vocab plain text), "
        "'table_columns' (drawn table), 'date_pair: true' (two-leading-"
        "dates plain text), or 'positioned_columns' (side-by-side unsigned "
        "amount columns) -- see natwest.yaml / santander.yaml / "
        "natwest_credit_card.yaml / capital_one.yaml."
    )


def import_pdf(
    conn: Connection,
    pdf_path: Path,
    bank: str,
    account_name: str,
    account_type: str,
    rules: list[Rule],
    formats_dir: Path,
) -> dict:
    fmt = load_pdf_format(bank, formats_dir)
    txns = parse_transactions(pdf_path, fmt)
    account_id = get_or_create_account(conn, institution=bank, account_type=account_type, name=account_name)

    inserted = updated = 0
    for txn in txns:
        category = categorize(txn["description"], None, rules)
        ext_id = _external_id(bank, account_name, txn["date"], txn["description"], txn["amount"])
        was_inserted = upsert_transaction(
            conn,
            account_id=account_id,
            date=txn["date"],
            amount=txn["amount"],
            description=txn["description"],
            merchant=None,
            category=category,
            source=f"pdf:{bank}",
            external_id=ext_id,
        )
        inserted += was_inserted
        updated += not was_inserted

    balance_recorded = False
    closing_balance = extract_closing_balance(pdf_path, fmt)
    if closing_balance is not None:
        statement_range = _infer_statement_range("\n".join(_extract_pages_text(pdf_path)))
        if statement_range:
            if fmt.get("balance_is_debt"):
                closing_balance = -closing_balance  # owed money counts against net worth
            record_balance(conn, account_id, statement_range[1].strftime("%Y-%m-%d"), closing_balance)
            balance_recorded = True

    conn.commit()
    return {"inserted": inserted, "updated": updated, "balance_recorded": balance_recorded}


def dry_run_summary(pdf_path: Path, fmt: dict) -> dict:
    """For CLI --dry-run: counts and the detected statement date range
    only, never real transaction content, so it's safe to paste back to
    anyone (including an AI assistant) while debugging a format mismatch.
    """
    pages_text = _extract_pages_text(pdf_path)
    statement_range = _infer_statement_range("\n".join(pages_text))
    txns = parse_transactions(pdf_path, fmt)
    return {
        "pages": len(pages_text),
        "text_line_count": sum(len(t.splitlines()) for t in pages_text),
        "statement_range": (
            [statement_range[0].isoformat(), statement_range[1].isoformat()]
            if statement_range
            else None
        ),
        "transactions_parsed": len(txns),
    }
