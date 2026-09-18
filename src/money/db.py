"""SQLite schema and data-access helpers.

Amount convention: pounds (not pence), negative = money out, positive =
money in. Every table lives in one local file (data/money.db by default),
never transmitted anywhere.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import yaml

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    institution TEXT NOT NULL,
    account_type TEXT NOT NULL,
    name TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'GBP',
    UNIQUE (institution, name)
);

CREATE TABLE IF NOT EXISTS categories (
    name TEXT PRIMARY KEY,
    parent TEXT
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    date TEXT NOT NULL,
    amount REAL NOT NULL,
    description TEXT NOT NULL,
    merchant TEXT,
    category TEXT NOT NULL DEFAULT 'Uncategorized',
    source TEXT NOT NULL,
    external_id TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_transactions_account_date
    ON transactions (account_id, date);

CREATE INDEX IF NOT EXISTS idx_transactions_category
    ON transactions (category);

CREATE TABLE IF NOT EXISTS balances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    snapshot_date TEXT NOT NULL,
    balance REAL NOT NULL,
    UNIQUE (account_id, snapshot_date)
);
"""


def get_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection, categories_config: Path | None = None) -> None:
    conn.executescript(SCHEMA)
    if categories_config and categories_config.exists():
        seed_categories(conn, categories_config)
    conn.commit()


def seed_categories(conn: sqlite3.Connection, categories_config: Path) -> None:
    """Upsert, not insert-or-ignore: this runs on every command (via
    init_db), so an edit to categories.yaml's `parent` (e.g. moving a
    category under Discretionary/Non-Discretionary) needs to actually
    apply to an already-seeded category, not be silently skipped.
    """
    data = yaml.safe_load(categories_config.read_text()) or {}
    for entry in data.get("categories", []):
        conn.execute(
            "INSERT INTO categories (name, parent) VALUES (?, ?) "
            "ON CONFLICT (name) DO UPDATE SET parent = excluded.parent",
            (entry["name"], entry.get("parent")),
        )


def get_or_create_account(
    conn: sqlite3.Connection,
    institution: str,
    account_type: str,
    name: str,
    currency: str = "GBP",
) -> int:
    cur = conn.execute(
        "SELECT id FROM accounts WHERE institution = ? AND name = ?",
        (institution, name),
    )
    row = cur.fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO accounts (institution, account_type, name, currency) "
        "VALUES (?, ?, ?, ?)",
        (institution, account_type, name, currency),
    )
    conn.commit()
    return cur.lastrowid


def upsert_transaction(
    conn: sqlite3.Connection,
    account_id: int,
    date: str,
    amount: float,
    description: str,
    merchant: str | None,
    category: str,
    source: str,
    external_id: str,
) -> bool:
    """Insert a transaction, or update it in place if external_id already
    exists (e.g. category corrected, description cleaned up).

    Returns True if a new row was inserted, False if an existing row was
    updated.
    """
    cur = conn.execute(
        "SELECT id FROM transactions WHERE external_id = ?", (external_id,)
    )
    existing = cur.fetchone()
    if existing:
        conn.execute(
            "UPDATE transactions SET account_id = ?, date = ?, amount = ?, "
            "description = ?, merchant = ?, category = ?, source = ? "
            "WHERE external_id = ?",
            (account_id, date, amount, description, merchant, category, source,
             external_id),
        )
        return False
    conn.execute(
        "INSERT INTO transactions "
        "(account_id, date, amount, description, merchant, category, source, "
        "external_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (account_id, date, amount, description, merchant, category, source,
         external_id),
    )
    return True


def record_balance(
    conn: sqlite3.Connection, account_id: int, snapshot_date: str, balance: float
) -> None:
    conn.execute(
        "INSERT INTO balances (account_id, snapshot_date, balance) "
        "VALUES (?, ?, ?) "
        "ON CONFLICT (account_id, snapshot_date) DO UPDATE SET balance = excluded.balance",
        (account_id, snapshot_date, balance),
    )


def last_imported_date(conn: sqlite3.Connection, account_id: int, source: str) -> str | None:
    cur = conn.execute(
        "SELECT MAX(date) AS max_date FROM transactions "
        "WHERE account_id = ? AND source = ?",
        (account_id, source),
    )
    row = cur.fetchone()
    return row["max_date"] if row else None
