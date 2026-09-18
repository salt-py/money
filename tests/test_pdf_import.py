from pathlib import Path

from money.categorize import load_rules
from money.db import get_connection, init_db
from money.importers.pdf_import import (
    _infer_statement_range,
    _resolve_day_month,
    _split_day_month,
    dry_run_summary,
    import_pdf,
    load_pdf_format,
)

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).parent.parent
PDF_FORMATS_DIR = REPO_ROOT / "config" / "pdf_formats"
# Synthetic rules made up for these tests -- not the real, gitignored,
# per-user config/rules.yaml (which won't even exist on a fresh clone).
RULES_PATH = FIXTURES / "rules.yaml"
SAMPLE_PDF = FIXTURES / "synthetic_natwest_statement.pdf"
SANTANDER_SAMPLE_PDF = FIXTURES / "synthetic_santander_statement.pdf"
NATWEST_CC_SAMPLE_PDF = FIXTURES / "synthetic_natwest_credit_card_statement.pdf"
CAPITAL_ONE_SAMPLE_PDF = FIXTURES / "synthetic_capital_one_statement.pdf"


def test_infer_statement_range_numeric_labels():
    text = "From\n01/08/2026\nTo\n31/08/2026\nDate of creation\n01/09/2026"
    start, end = _infer_statement_range(text)
    assert start.isoformat() == "2026-08-01"
    assert end.isoformat() == "2026-08-31"


def test_infer_statement_range_ordinal_labels():
    text = (
        "Account summary as at: 11th September 2026 for card number ending 0000\n"
        "Previous balance as at 13th August 2026: £1,000.00"
    )
    start, end = _infer_statement_range(text)
    assert start.isoformat() == "2026-08-13"
    assert end.isoformat() == "2026-09-11"


def test_infer_statement_range_ordinal_label_without_previous_balance():
    text = "Statement Date: 11th September 2026"
    start, end = _infer_statement_range(text)
    assert start.isoformat() == end.isoformat() == "2026-09-11"


def test_infer_statement_range_month_range_label():
    start, end = _infer_statement_range("10 August - 09 September 2026")
    assert start.isoformat() == "2026-08-10"
    assert end.isoformat() == "2026-09-09"


def test_infer_statement_range_month_range_label_no_spaces():
    # Real quirk: pdfplumber sometimes drops the space between a digit and
    # the following letter depending on the PDF's font kerning.
    start, end = _infer_statement_range("10August -09September 2026")
    assert start.isoformat() == "2026-08-10"
    assert end.isoformat() == "2026-09-09"


def test_infer_statement_range_two_digit_year_single_date():
    start, end = _infer_statement_range("Statement date 10 September 26")
    assert start.isoformat() == end.isoformat() == "2026-09-10"


def test_split_day_month_handles_jammed_and_spaced():
    assert _split_day_month("03 SEP") == ("03", "SEP")
    assert _split_day_month("03SEP") == ("03", "SEP")
    assert _split_day_month("garbage") is None


def test_resolve_day_month_within_range():
    from datetime import date

    rng = (date(2026, 8, 1), date(2026, 8, 31))
    assert _resolve_day_month(15, "Aug", rng) == "2026-08-15"


def test_resolve_day_month_handles_year_boundary():
    from datetime import date

    rng = (date(2025, 12, 10), date(2026, 1, 10))
    assert _resolve_day_month(20, "Dec", rng) == "2025-12-20"
    assert _resolve_day_month(5, "Jan", rng) == "2026-01-05"


def test_dry_run_summary_reports_structure_only():
    fmt = load_pdf_format("natwest", PDF_FORMATS_DIR)
    summary = dry_run_summary(SAMPLE_PDF, fmt)
    assert summary["pages"] == 1
    assert summary["statement_range"] == ["2026-08-01", "2026-08-31"]
    assert summary["transactions_parsed"] == 3


def test_import_pdf_inserts_and_categorizes(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    rules = load_rules(RULES_PATH)

    result = import_pdf(
        conn,
        pdf_path=SAMPLE_PDF,
        bank="natwest",
        account_name="Test NatWest Current Account",
        account_type="current",
        rules=rules,
        formats_dir=PDF_FORMATS_DIR,
    )
    assert result["inserted"] == 3
    assert result["updated"] == 0

    rows = conn.execute("SELECT date, amount, category FROM transactions ORDER BY date").fetchall()
    assert rows[0]["date"] == "2026-08-01"
    assert rows[0]["amount"] == -800.00
    assert rows[0]["category"] == "Household Contribution"  # matches "EXAMPLE KIDS CLUB" in fixtures/rules.yaml
    assert rows[1]["date"] == "2026-08-02"
    assert rows[1]["amount"] == 2500.00
    assert rows[1]["category"] == "Income"
    assert rows[2]["date"] == "2026-08-03"
    assert rows[2]["amount"] == -32.10
    assert rows[2]["category"] == "Groceries"


def test_import_pdf_is_idempotent_on_reimport(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    rules = load_rules(RULES_PATH)
    kwargs = dict(
        pdf_path=SAMPLE_PDF,
        bank="natwest",
        account_name="Test NatWest Current Account",
        account_type="current",
        rules=rules,
        formats_dir=PDF_FORMATS_DIR,
    )

    import_pdf(conn, **kwargs)
    second = import_pdf(conn, **kwargs)

    assert second["inserted"] == 0
    assert second["updated"] == 3


def test_natwest_credit_card_dry_run_summary():
    fmt = load_pdf_format("natwest_credit_card", PDF_FORMATS_DIR)
    summary = dry_run_summary(NATWEST_CC_SAMPLE_PDF, fmt)
    assert summary["statement_range"] == ["2026-08-10", "2026-09-09"]
    assert summary["transactions_parsed"] == 4


def test_natwest_credit_card_import_handles_credit_and_jammed_dates(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    rules = load_rules(RULES_PATH)

    result = import_pdf(
        conn,
        pdf_path=NATWEST_CC_SAMPLE_PDF,
        bank="natwest_credit_card",
        account_name="Test NatWest Credit Card",
        account_type="credit_card",
        rules=rules,
        formats_dir=PDF_FORMATS_DIR,
    )
    # 4 real rows: the FX continuation line ("28.22 USD ..."), "Sub-Total"
    # and "NEW BALANCE" summary lines are all correctly excluded since they
    # don't start with two leading dates.
    assert result["inserted"] == 4
    assert result["updated"] == 0

    rows = conn.execute("SELECT date, amount FROM transactions ORDER BY date, amount").fetchall()
    assert rows[0]["date"] == "2026-09-03"
    assert rows[0]["amount"] == -10.99  # bare amount -> charge -> spend
    assert rows[1]["date"] == "2026-09-03"
    assert rows[1]["amount"] == 100.00  # trailing "-" -> credit -> positive
    assert rows[2]["date"] == "2026-09-06"
    assert rows[2]["amount"] == -20.93
    assert rows[3]["date"] == "2026-09-07"
    assert rows[3]["amount"] == -0.58


def test_natwest_credit_card_import_is_idempotent_on_reimport(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    rules = load_rules(RULES_PATH)
    kwargs = dict(
        pdf_path=NATWEST_CC_SAMPLE_PDF,
        bank="natwest_credit_card",
        account_name="Test NatWest Credit Card",
        account_type="credit_card",
        rules=rules,
        formats_dir=PDF_FORMATS_DIR,
    )

    import_pdf(conn, **kwargs)
    second = import_pdf(conn, **kwargs)

    assert second["inserted"] == 0
    assert second["updated"] == 4


def test_santander_dry_run_summary():
    fmt = load_pdf_format("santander", PDF_FORMATS_DIR)
    summary = dry_run_summary(SANTANDER_SAMPLE_PDF, fmt)
    assert summary["statement_range"] == ["2026-08-13", "2026-09-11"]
    assert summary["transactions_parsed"] == 3


def test_santander_import_filters_summary_rows_and_flips_sign(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    rules = load_rules(RULES_PATH)

    result = import_pdf(
        conn,
        pdf_path=SANTANDER_SAMPLE_PDF,
        bank="santander",
        account_name="Test Santander Card",
        account_type="credit_card",
        rules=rules,
        formats_dir=PDF_FORMATS_DIR,
    )
    # 3 real rows: "Balance brought forward"/"Total of New Transactions"
    # (matched by skip_description_patterns) and the blank-amount "Balance
    # ... Interest 0.000%..." summary row are all correctly excluded.
    assert result["inserted"] == 3
    assert result["updated"] == 0

    rows = conn.execute("SELECT date, description, amount FROM transactions ORDER BY date").fetchall()
    assert rows[0]["date"] == "2026-08-01"
    assert rows[0]["amount"] == -25.50  # positive charge on statement -> spend
    assert rows[1]["date"] == "2026-08-05"
    assert rows[1]["amount"] == -3.00
    # "Interest" has no date of its own -> falls back to the statement date.
    assert rows[2]["date"] == "2026-09-11"
    assert rows[2]["description"] == "Interest"
    assert rows[2]["amount"] == -2.10


def test_santander_import_is_idempotent_on_reimport(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    rules = load_rules(RULES_PATH)
    kwargs = dict(
        pdf_path=SANTANDER_SAMPLE_PDF,
        bank="santander",
        account_name="Test Santander Card",
        account_type="credit_card",
        rules=rules,
        formats_dir=PDF_FORMATS_DIR,
    )

    import_pdf(conn, **kwargs)
    second = import_pdf(conn, **kwargs)

    assert second["inserted"] == 0
    assert second["updated"] == 3


def test_capital_one_dry_run_summary():
    fmt = load_pdf_format("capital_one", PDF_FORMATS_DIR)
    summary = dry_run_summary(CAPITAL_ONE_SAMPLE_PDF, fmt)
    assert summary["statement_range"] == ["2026-09-10", "2026-09-10"]
    assert summary["transactions_parsed"] == 2


def test_capital_one_import_uses_column_position_for_sign(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    rules = load_rules(RULES_PATH)

    result = import_pdf(
        conn,
        pdf_path=CAPITAL_ONE_SAMPLE_PDF,
        bank="capital_one",
        account_name="Test Capital One Card",
        account_type="credit_card",
        rules=rules,
        formats_dir=PDF_FORMATS_DIR,
    )
    # 2 real rows -- the "STATEMENT TOTALS" row (both columns filled at
    # once) is correctly excluded via skip_description_patterns.
    assert result["inserted"] == 2
    assert result["updated"] == 0

    rows = conn.execute("SELECT date, description, amount FROM transactions ORDER BY date").fetchall()
    assert rows[0]["date"] == "2026-08-16"
    assert rows[0]["amount"] == -63.99  # right-hand "Paid out" column -> spend
    assert rows[1]["date"] == "2026-09-02"
    assert rows[1]["amount"] == 244.60  # left-hand "Paid in" column -> credit


def test_capital_one_import_is_idempotent_on_reimport(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    rules = load_rules(RULES_PATH)
    kwargs = dict(
        pdf_path=CAPITAL_ONE_SAMPLE_PDF,
        bank="capital_one",
        account_name="Test Capital One Card",
        account_type="credit_card",
        rules=rules,
        formats_dir=PDF_FORMATS_DIR,
    )

    import_pdf(conn, **kwargs)
    second = import_pdf(conn, **kwargs)

    assert second["inserted"] == 0
    assert second["updated"] == 2


def test_import_pdf_records_balance_as_negative_debt(tmp_path):
    """All three credit card formats have a balance_label_pattern -- the
    extracted closing balance should land in the balances table as a
    negative (debt reduces net worth), dated to the statement's own end
    date, for each of them.
    """
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    rules = load_rules(RULES_PATH)

    cases = [
        (SANTANDER_SAMPLE_PDF, "santander", "credit_card", -930.60, "2026-09-11"),
        (NATWEST_CC_SAMPLE_PDF, "natwest_credit_card", "credit_card", -32.50, "2026-09-09"),
        (CAPITAL_ONE_SAMPLE_PDF, "capital_one", "credit_card", -4000.00, "2026-09-10"),
    ]
    for pdf_path, bank, account_type, expected_balance, expected_date in cases:
        result = import_pdf(
            conn,
            pdf_path=pdf_path,
            bank=bank,
            account_name=f"Test {bank}",
            account_type=account_type,
            rules=rules,
            formats_dir=PDF_FORMATS_DIR,
        )
        assert result["balance_recorded"] is True

        row = conn.execute(
            "SELECT balance, snapshot_date FROM balances b "
            "JOIN accounts a ON a.id = b.account_id WHERE a.name = ?",
            (f"Test {bank}",),
        ).fetchone()
        assert row["balance"] == expected_balance
        assert row["snapshot_date"] == expected_date


def test_import_pdf_no_balance_pattern_means_no_balance_recorded(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    rules = load_rules(RULES_PATH)

    result = import_pdf(
        conn,
        pdf_path=SAMPLE_PDF,
        bank="natwest",
        account_name="Test NatWest Current Account",
        account_type="current",
        rules=rules,
        formats_dir=PDF_FORMATS_DIR,
    )
    assert result["balance_recorded"] is False
