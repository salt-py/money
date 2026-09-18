from money.db import get_connection, get_or_create_account, init_db, upsert_transaction
from money.reports import budget_vs_actual


def make_conn(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    return conn


def test_budget_vs_actual_with_no_budget_prints_hint(tmp_path, capsys):
    conn = make_conn(tmp_path)
    budget_vs_actual(conn, month="2026-08", budget={})
    out = capsys.readouterr().out
    assert "budget suggest --save" in out


def test_budget_vs_actual_flags_overspend(tmp_path, capsys):
    conn = make_conn(tmp_path)
    account_id = get_or_create_account(conn, "FakeBank", "current", "Main")
    upsert_transaction(conn, account_id, "2026-08-10", -250.0, "SHOP A", None, "Groceries", "test", "e1")
    conn.commit()

    budget_vs_actual(conn, month="2026-08", budget={"Groceries": 200.0})
    out = capsys.readouterr().out
    assert "Groceries" in out
    assert "OVER" in out


def test_budget_vs_actual_includes_categories_with_no_spend(tmp_path, capsys):
    conn = make_conn(tmp_path)
    budget_vs_actual(conn, month="2026-08", budget={"Eating Out": 80.0})
    out = capsys.readouterr().out
    assert "Eating Out" in out
    assert "80.00" in out


def test_budget_vs_actual_includes_unbudgeted_spend_categories(tmp_path, capsys):
    conn = make_conn(tmp_path)
    account_id = get_or_create_account(conn, "FakeBank", "current", "Main")
    upsert_transaction(conn, account_id, "2026-08-10", -30.0, "SURPRISE SHOP", None, "Shopping", "test", "e1")
    conn.commit()

    # No budget set for Shopping at all -- should still show up (budget 0).
    budget_vs_actual(conn, month="2026-08", budget={"Groceries": 200.0})
    out = capsys.readouterr().out
    assert "Shopping" in out


def test_budget_vs_actual_shows_debit_and_credit_separately(tmp_path, capsys):
    conn = make_conn(tmp_path)
    account_id = get_or_create_account(conn, "FakeBank", "current", "Main")
    # A purchase and a partial refund in the same category, same month.
    upsert_transaction(conn, account_id, "2026-08-05", -100.0, "SHOP A", None, "Shopping", "test", "e1")
    upsert_transaction(conn, account_id, "2026-08-12", 20.0, "SHOP A REFUND", None, "Shopping", "test", "e2")
    conn.commit()

    budget_vs_actual(conn, month="2026-08", budget={"Shopping": 100.0})
    lines = capsys.readouterr().out.splitlines()
    shopping_line = next(line for line in lines if line.strip().startswith("Shopping"))
    cells = shopping_line.split()
    # Category, budget, out, in, net, variance
    assert cells[1] == "100.00"  # budget
    assert cells[2] == "100.00"  # out (the purchase, not netted against the refund)
    assert cells[3] == "20.00"  # in (the refund, visible on its own)
    assert cells[4] == "80.00"  # net = out - in
    assert cells[5] == "20.00"  # variance = budget - net, under budget once refund counted
