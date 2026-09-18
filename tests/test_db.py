from money.db import (
    get_connection,
    get_or_create_account,
    init_db,
    last_imported_date,
    record_balance,
    seed_categories,
    upsert_transaction,
)


def make_conn(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    return conn


def test_init_db_creates_tables(tmp_path):
    conn = make_conn(tmp_path)
    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"accounts", "transactions", "balances", "categories"} <= tables


def test_get_or_create_account_is_idempotent(tmp_path):
    conn = make_conn(tmp_path)
    id1 = get_or_create_account(conn, "Fake Bank", "current", "Main")
    id2 = get_or_create_account(conn, "Fake Bank", "current", "Main")
    assert id1 == id2


def test_upsert_transaction_inserts_then_updates(tmp_path):
    conn = make_conn(tmp_path)
    account_id = get_or_create_account(conn, "Fake Bank", "current", "Main")

    was_inserted = upsert_transaction(
        conn, account_id, "2026-08-01", -10.0, "Test Shop", "Test Shop",
        "Shopping", "test", "ext-1",
    )
    conn.commit()
    assert was_inserted is True

    was_inserted_again = upsert_transaction(
        conn, account_id, "2026-08-01", -10.0, "Test Shop", "Test Shop",
        "Groceries", "test", "ext-1",
    )
    conn.commit()
    assert was_inserted_again is False

    row = conn.execute(
        "SELECT category FROM transactions WHERE external_id = 'ext-1'"
    ).fetchone()
    assert row["category"] == "Groceries"

    count = conn.execute("SELECT COUNT(*) AS n FROM transactions").fetchone()["n"]
    assert count == 1


def test_last_imported_date(tmp_path):
    conn = make_conn(tmp_path)
    account_id = get_or_create_account(conn, "Fake Bank", "current", "Main")
    assert last_imported_date(conn, account_id, "test") is None

    upsert_transaction(
        conn, account_id, "2026-08-05", -5.0, "A", None, "Uncategorized",
        "test", "ext-a",
    )
    upsert_transaction(
        conn, account_id, "2026-08-10", -5.0, "B", None, "Uncategorized",
        "test", "ext-b",
    )
    conn.commit()
    assert last_imported_date(conn, account_id, "test") == "2026-08-10"


def test_record_balance_upserts_per_day(tmp_path):
    conn = make_conn(tmp_path)
    account_id = get_or_create_account(conn, "Fake Bank", "current", "Main")
    record_balance(conn, account_id, "2026-08-01", 100.0)
    record_balance(conn, account_id, "2026-08-01", 150.0)
    conn.commit()
    rows = conn.execute("SELECT balance FROM balances WHERE account_id = ?", (account_id,)).fetchall()
    assert len(rows) == 1
    assert rows[0]["balance"] == 150.0


def test_seed_categories_updates_parent_on_existing_category(tmp_path):
    """Not just insert-or-ignore: this runs on every command via init_db,
    so an edit to categories.yaml (e.g. moving a category under
    Discretionary/Non-Discretionary) must actually apply to a category
    that was already seeded in a prior run.
    """
    conn = make_conn(tmp_path)
    yaml_path = tmp_path / "categories.yaml"

    yaml_path.write_text("categories:\n  - name: Shopping\n    parent: null\n")
    seed_categories(conn, yaml_path)
    conn.commit()
    row = conn.execute("SELECT parent FROM categories WHERE name = 'Shopping'").fetchone()
    assert row["parent"] is None

    yaml_path.write_text("categories:\n  - name: Shopping\n    parent: Discretionary\n")
    seed_categories(conn, yaml_path)
    conn.commit()
    row = conn.execute("SELECT parent FROM categories WHERE name = 'Shopping'").fetchone()
    assert row["parent"] == "Discretionary"
