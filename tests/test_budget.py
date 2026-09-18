from datetime import date

from money.budget import _months_before, load_budget, save_budget, suggest_budget
from money.db import get_connection, get_or_create_account, init_db, upsert_transaction


def make_conn(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    return conn


def test_months_before_same_year():
    assert _months_before(date(2026, 9, 15), 3) == date(2026, 6, 1)


def test_months_before_crosses_year_boundary():
    assert _months_before(date(2026, 2, 15), 3) == date(2025, 11, 1)


def test_suggest_budget_averages_over_window(tmp_path):
    conn = make_conn(tmp_path)
    account_id = get_or_create_account(conn, "FakeBank", "current", "Main")

    # 3 months of Groceries spend: 100, 200, 300 -> total 600, avg 200/mo
    # over a 3-month window.
    upsert_transaction(conn, account_id, "2026-06-10", -100.0, "SHOP A", None, "Groceries", "test", "e1")
    upsert_transaction(conn, account_id, "2026-07-10", -200.0, "SHOP A", None, "Groceries", "test", "e2")
    upsert_transaction(conn, account_id, "2026-08-10", -300.0, "SHOP A", None, "Groceries", "test", "e3")
    conn.commit()

    result = suggest_budget(conn, months=3, as_of=date(2026, 9, 15))
    assert result["start_date"] == "2026-06-01"
    groceries = next(c for c in result["categories"] if c["category"] == "Groceries")
    assert groceries["total"] == 600.0
    assert groceries["monthly_average"] == 200.0
    assert groceries["transaction_count"] == 3


def test_suggest_budget_excludes_credit_card_payment_by_default(tmp_path):
    conn = make_conn(tmp_path)
    account_id = get_or_create_account(conn, "FakeBank", "current", "Main")
    upsert_transaction(conn, account_id, "2026-08-10", -50.0, "PAYMENT", None, "Credit Card Payment", "test", "e1")
    conn.commit()

    result = suggest_budget(conn, months=3, as_of=date(2026, 9, 15))
    assert result["categories"] == []


def test_suggest_budget_ignores_income_and_old_transactions(tmp_path):
    conn = make_conn(tmp_path)
    account_id = get_or_create_account(conn, "FakeBank", "current", "Main")
    upsert_transaction(conn, account_id, "2026-08-10", 2000.0, "SALARY", None, "Income", "test", "e1")
    upsert_transaction(conn, account_id, "2026-01-10", -999.0, "OLD SHOP", None, "Shopping", "test", "e2")
    conn.commit()

    result = suggest_budget(conn, months=3, as_of=date(2026, 9, 15))
    assert result["categories"] == []


def test_load_budget_missing_file_returns_empty(tmp_path):
    assert load_budget(tmp_path / "nonexistent.yaml") == {}


def test_save_and_load_budget_round_trip(tmp_path):
    path = tmp_path / "budget.yaml"
    save_budget(path, {"Groceries": 200.567, "Eating Out": 50.0})

    loaded = load_budget(path)
    assert loaded == {"Groceries": 200.57, "Eating Out": 50.0}
    # Comment header present and file is otherwise sane to read by hand.
    assert path.read_text().startswith("#")
