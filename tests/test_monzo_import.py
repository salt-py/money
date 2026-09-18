"""Tests for money.importers.monzo's account-naming logic, including
run_import's account_name_overrides -- exercised against a fake client, no
real network calls or credentials involved.
"""

from money.categorize import Rule
from money.db import get_connection, init_db
from money.importers import monzo


def test_parse_account_name_overrides_basic():
    assert monzo.parse_account_name_overrides("acc_1:Household Account") == {
        "acc_1": "Household Account"
    }


def test_parse_account_name_overrides_multiple():
    result = monzo.parse_account_name_overrides("acc_1:Household Account,acc_2:Savings")
    assert result == {"acc_1": "Household Account", "acc_2": "Savings"}


def test_parse_account_name_overrides_empty_string():
    assert monzo.parse_account_name_overrides("") == {}


def test_parse_account_name_overrides_ignores_malformed_entries():
    # No colon -- skipped rather than raising.
    assert monzo.parse_account_name_overrides("acc_1,acc_2:Savings") == {"acc_2": "Savings"}


class FakeMonzoClient:
    def __init__(self, accounts):
        self._accounts = accounts

    def list_accounts(self):
        return self._accounts

    def list_transactions(self, account_id, since=None):
        return []

    def balance(self, account_id):
        return {"balance": 0.0, "currency": "GBP"}


def test_run_import_uses_override_when_description_is_empty(tmp_path, monkeypatch):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)

    fake_client = FakeMonzoClient([{"id": "user_abc123", "description": "", "type": "current", "closed": False}])
    monkeypatch.setattr(monzo, "ensure_fresh_client", lambda *a, **kw: fake_client)

    monzo.run_import(
        conn, "client_id", "client_secret", tmp_path / "tokens.json", rules=[],
        account_name_overrides={"user_abc123": "Household Account"},
    )

    row = conn.execute("SELECT name FROM accounts WHERE institution = 'Monzo'").fetchone()
    assert row["name"] == "Household Account"


def test_run_import_falls_back_to_raw_id_without_override(tmp_path, monkeypatch):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)

    fake_client = FakeMonzoClient([{"id": "user_abc123", "description": "", "type": "current", "closed": False}])
    monkeypatch.setattr(monzo, "ensure_fresh_client", lambda *a, **kw: fake_client)

    monzo.run_import(conn, "client_id", "client_secret", tmp_path / "tokens.json", rules=[])

    row = conn.execute("SELECT name FROM accounts WHERE institution = 'Monzo'").fetchone()
    assert row["name"] == "user_abc123"


def test_run_import_override_wins_even_over_a_real_description(tmp_path, monkeypatch):
    """An override is a deliberate, authoritative choice, not just a
    fallback for a missing description -- if you've set one, it wins even
    when Monzo does provide its own description for the account.
    """
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)

    fake_client = FakeMonzoClient(
        [{"id": "user_abc123", "description": "Personal Account", "type": "current", "closed": False}]
    )
    monkeypatch.setattr(monzo, "ensure_fresh_client", lambda *a, **kw: fake_client)

    monzo.run_import(
        conn, "client_id", "client_secret", tmp_path / "tokens.json", rules=[],
        account_name_overrides={"user_abc123": "Household Account"},
    )

    row = conn.execute("SELECT name FROM accounts WHERE institution = 'Monzo'").fetchone()
    assert row["name"] == "Household Account"
