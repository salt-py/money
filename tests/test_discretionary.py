from money.db import get_connection, get_or_create_account, init_db, upsert_transaction
from money.discretionary import compute_discretionary, resolve_bucket

CATEGORIES_SQL = """
INSERT INTO categories (name, parent) VALUES
    ('Discretionary', NULL),
    ('Non-Discretionary', NULL),
    ('Income', NULL),
    ('Bills & Utilities', 'Non-Discretionary'),
    ('Utilities', 'Bills & Utilities'),
    ('Household Contribution', 'Non-Discretionary'),
    ('Eating Out', 'Discretionary'),
    ('Shopping', 'Discretionary'),
    ('Credit Card Payment', NULL),
    ('Interest', NULL),
    ('Transfers', NULL),
    ('Uncategorized', NULL)
"""


def make_conn(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    conn.executescript(CATEGORIES_SQL)
    conn.commit()
    return conn


def test_compute_discretionary_basic_breakdown(tmp_path):
    conn = make_conn(tmp_path)
    acc = get_or_create_account(conn, "FakeBank", "current", "Main")
    upsert_transaction(conn, acc, "2026-08-01", 2500.0, "SALARY", None, "Income", "test", "e1")
    upsert_transaction(conn, acc, "2026-08-02", -800.0, "RENT", None, "Household Contribution", "test", "e2")
    upsert_transaction(conn, acc, "2026-08-03", -150.0, "GAS", None, "Bills & Utilities", "test", "e3")
    upsert_transaction(conn, acc, "2026-08-04", -60.0, "RESTAURANT", None, "Eating Out", "test", "e4")
    conn.commit()

    result = compute_discretionary(conn, "2026-08")
    assert result["income"] == 2500.0
    assert result["essential_breakdown"] == {"Household Contribution": 800.0, "Bills & Utilities": 150.0}
    assert result["essential_total"] == 950.0
    assert result["discretionary_available"] == 1550.0
    assert result["discretionary_breakdown"] == {"Eating Out": 60.0}
    assert result["discretionary_total"] == 60.0
    assert result["surplus"] == 1490.0


def test_compute_discretionary_excludes_unclassified_categories(tmp_path):
    conn = make_conn(tmp_path)
    acc = get_or_create_account(conn, "FakeBank", "current", "Main")
    upsert_transaction(conn, acc, "2026-08-01", 2000.0, "SALARY", None, "Income", "test", "e1")
    upsert_transaction(conn, acc, "2026-08-02", -300.0, "CARD PAYMENT", None, "Credit Card Payment", "test", "e2")
    upsert_transaction(conn, acc, "2026-08-03", -50.0, "OD INTEREST", None, "Interest", "test", "e3")
    upsert_transaction(conn, acc, "2026-08-04", -100.0, "SAVINGS XFER", None, "Transfers", "test", "e4")
    conn.commit()

    result = compute_discretionary(conn, "2026-08")
    assert result["essential_breakdown"] == {}
    assert result["discretionary_breakdown"] == {}
    assert result["essential_total"] == 0.0
    assert result["discretionary_total"] == 0.0
    # Not silently lost -- just not counted in either bucket.
    assert result["discretionary_available"] == 2000.0


def test_compute_discretionary_reports_uncategorized_separately(tmp_path):
    conn = make_conn(tmp_path)
    acc = get_or_create_account(conn, "FakeBank", "current", "Main")
    upsert_transaction(conn, acc, "2026-08-01", 1000.0, "SALARY", None, "Income", "test", "e1")
    upsert_transaction(conn, acc, "2026-08-02", -75.0, "MYSTERY CO", None, "Uncategorized", "test", "e2")
    conn.commit()

    result = compute_discretionary(conn, "2026-08")
    assert result["uncategorized_net"] == 75.0
    assert result["essential_breakdown"] == {}
    assert result["discretionary_breakdown"] == {}


def test_compute_discretionary_subtracts_debt_commitment(tmp_path):
    conn = make_conn(tmp_path)
    acc = get_or_create_account(conn, "FakeBank", "current", "Main")
    upsert_transaction(conn, acc, "2026-08-01", 2000.0, "SALARY", None, "Income", "test", "e1")
    conn.commit()

    result = compute_discretionary(conn, "2026-08", debt_minimum_total=150.0, debt_extra=200.0)
    assert result["discretionary_available"] == 2000.0 - 150.0 - 200.0


def test_compute_discretionary_nets_refunds_within_a_category(tmp_path):
    conn = make_conn(tmp_path)
    acc = get_or_create_account(conn, "FakeBank", "current", "Main")
    upsert_transaction(conn, acc, "2026-08-01", -100.0, "SHOP", None, "Shopping", "test", "e1")
    upsert_transaction(conn, acc, "2026-08-02", 20.0, "SHOP REFUND", None, "Shopping", "test", "e2")
    conn.commit()

    result = compute_discretionary(conn, "2026-08")
    assert result["discretionary_breakdown"]["Shopping"] == 80.0


def test_compute_discretionary_surplus_negative_when_overspent(tmp_path):
    conn = make_conn(tmp_path)
    acc = get_or_create_account(conn, "FakeBank", "current", "Main")
    upsert_transaction(conn, acc, "2026-08-01", 500.0, "SALARY", None, "Income", "test", "e1")
    upsert_transaction(conn, acc, "2026-08-02", -400.0, "RENT", None, "Household Contribution", "test", "e2")
    upsert_transaction(conn, acc, "2026-08-03", -200.0, "RESTAURANT", None, "Eating Out", "test", "e3")
    conn.commit()

    # income 500 - essential 400 = 100 available, but 200 actually spent discretionary
    result = compute_discretionary(conn, "2026-08")
    assert result["discretionary_available"] == 100.0
    assert result["discretionary_total"] == 200.0
    assert result["surplus"] == -100.0


def test_compute_discretionary_walks_multi_level_parent_chain(tmp_path):
    # "Utilities" -> parent "Bills & Utilities" -> parent "Non-Discretionary"
    # (two hops, not a direct parent) should still count as essential.
    conn = make_conn(tmp_path)
    acc = get_or_create_account(conn, "FakeBank", "current", "Main")
    upsert_transaction(conn, acc, "2026-08-01", 1000.0, "SALARY", None, "Income", "test", "e1")
    upsert_transaction(conn, acc, "2026-08-02", -90.0, "ENERGY CO", None, "Utilities", "test", "e2")
    conn.commit()

    result = compute_discretionary(conn, "2026-08")
    assert result["essential_breakdown"] == {"Utilities": 90.0}
    assert result["discretionary_available"] == 910.0


def test_resolve_bucket_direct_parent():
    parent_map = {"Shopping": "Discretionary", "Discretionary": None}
    assert resolve_bucket("Shopping", parent_map) == "Discretionary"


def test_resolve_bucket_multi_hop():
    parent_map = {
        "Utilities": "Bills & Utilities",
        "Bills & Utilities": "Non-Discretionary",
        "Non-Discretionary": None,
    }
    assert resolve_bucket("Utilities", parent_map) == "Non-Discretionary"


def test_resolve_bucket_unknown_category_returns_none():
    assert resolve_bucket("Some New Category", {}) is None


def test_resolve_bucket_dead_end_returns_none():
    parent_map = {"Transfers": None}
    assert resolve_bucket("Transfers", parent_map) is None


def test_resolve_bucket_cycle_returns_none_instead_of_looping():
    parent_map = {"A": "B", "B": "A"}
    assert resolve_bucket("A", parent_map) is None
