"""Integration tests for `money budget` / `money report budget`, driven
against a synthetic DB -- never real data.
"""

from datetime import date
from types import SimpleNamespace

from money import cli
from money.db import get_or_create_account, init_db, upsert_transaction


def setup_fixture_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    categories_path = tmp_path / "categories.yaml"
    budget_path = tmp_path / "budget.yaml"
    categories_path.write_text("categories:\n  - name: Groceries\n    parent: null\n")

    monkeypatch.setattr(cli, "DB_PATH", db_path)
    monkeypatch.setattr(cli, "CATEGORIES_CONFIG", categories_path)
    monkeypatch.setattr(cli, "BUDGET_CONFIG", budget_path)

    conn = cli._open_db()
    account_id = get_or_create_account(conn, "FakeBank", "current", "Main")
    # `suggest` defaults to averaging against date.today(), so use today's
    # date here rather than a fixed one -- keeps this test valid regardless
    # of when it's run, without needing to thread an as_of override through
    # the CLI layer just for testing.
    today = date.today().isoformat()
    upsert_transaction(conn, account_id, today, -200.0, "SHOP A", None, "Groceries", "test", "e1")
    conn.commit()
    conn.close()
    return budget_path


def test_budget_suggest_prints_without_saving(monkeypatch, tmp_path, capsys):
    budget_path = setup_fixture_db(monkeypatch, tmp_path)

    cli.cmd_budget(SimpleNamespace(budget_action="suggest", months=3, save=False))

    out = capsys.readouterr().out
    assert "Groceries" in out
    assert not budget_path.exists()


def test_budget_suggest_save_writes_file(monkeypatch, tmp_path):
    budget_path = setup_fixture_db(monkeypatch, tmp_path)

    cli.cmd_budget(SimpleNamespace(budget_action="suggest", months=3, save=True))

    assert budget_path.exists()
    from money.budget import load_budget

    budget = load_budget(budget_path)
    assert "Groceries" in budget


def test_budget_show_with_no_saved_budget(monkeypatch, tmp_path, capsys):
    setup_fixture_db(monkeypatch, tmp_path)

    cli.cmd_budget(SimpleNamespace(budget_action="show"))

    assert "No budget saved yet" in capsys.readouterr().out


def test_budget_show_after_save(monkeypatch, tmp_path, capsys):
    setup_fixture_db(monkeypatch, tmp_path)
    cli.cmd_budget(SimpleNamespace(budget_action="suggest", months=3, save=True))
    capsys.readouterr()  # discard suggest output

    cli.cmd_budget(SimpleNamespace(budget_action="show"))

    assert "Groceries" in capsys.readouterr().out


def test_report_budget_compares_against_saved_budget(monkeypatch, tmp_path, capsys):
    setup_fixture_db(monkeypatch, tmp_path)
    cli.cmd_budget(SimpleNamespace(budget_action="suggest", months=3, save=True))
    capsys.readouterr()

    current_month = date.today().isoformat()[:7]
    cli.cmd_report(SimpleNamespace(report="budget", month=current_month))

    out = capsys.readouterr().out
    assert "Groceries" in out
    assert "TOTAL" in out
