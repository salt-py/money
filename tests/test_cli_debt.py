"""Integration tests for `money debt`, driven with scripted input against
synthetic data -- never real data.
"""

from types import SimpleNamespace

from money import cli
from money.db import get_or_create_account, init_db, record_balance


def setup_fixture_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    categories_path = tmp_path / "categories.yaml"
    debt_path = tmp_path / "debt.yaml"
    categories_path.write_text("categories:\n  - name: Uncategorized\n    parent: null\n")

    monkeypatch.setattr(cli, "DB_PATH", db_path)
    monkeypatch.setattr(cli, "CATEGORIES_CONFIG", categories_path)
    monkeypatch.setattr(cli, "DEBT_CONFIG", debt_path)

    conn = cli._open_db()
    account_id = get_or_create_account(conn, "FakeCard", "credit_card", "Fake Card")
    record_balance(conn, account_id, "2026-09-01", -500.0)
    conn.commit()
    conn.close()
    return debt_path


def test_debt_setup_auto_detects_and_saves(monkeypatch, tmp_path):
    debt_path = setup_fixture_db(monkeypatch, tmp_path)

    # APR for the auto-detected "Fake Card", min payment, then decline
    # adding any manual debts.
    responses = iter(["20.0", "25.0", "n", "n"])
    monkeypatch.setattr("builtins.input", lambda *_: next(responses))

    cli.cmd_debt(SimpleNamespace(debt_action="setup"))

    from money.debt import load_debts

    debts = load_debts(debt_path)
    assert debts == {"Fake Card": {"balance": 500.0, "apr": 20.0, "min_payment": 25.0}}


def test_debt_setup_can_skip_auto_detected_account(monkeypatch, tmp_path):
    debt_path = setup_fixture_db(monkeypatch, tmp_path)

    responses = iter(["", "n"])  # blank APR with no prior value -> skip; decline manual add
    monkeypatch.setattr("builtins.input", lambda *_: next(responses))

    cli.cmd_debt(SimpleNamespace(debt_action="setup"))

    from money.debt import load_debts

    assert load_debts(debt_path) == {}


def test_debt_setup_can_add_manual_debt(monkeypatch, tmp_path, capsys):
    debt_path = setup_fixture_db(monkeypatch, tmp_path)

    responses = iter([
        "20.0", "25.0", "n",  # auto-detected Fake Card (decline promo)
        "y", "Fake Overdraft", "2000", "39.9", "0", "n",  # manual entry (decline promo)
        "n",  # no more manual entries
    ])
    monkeypatch.setattr("builtins.input", lambda *_: next(responses))

    cli.cmd_debt(SimpleNamespace(debt_action="setup"))

    from money.debt import load_debts

    debts = load_debts(debt_path)
    assert debts["Fake Card"] == {"balance": 500.0, "apr": 20.0, "min_payment": 25.0}
    assert debts["Fake Overdraft"] == {"balance": 2000.0, "apr": 39.9, "min_payment": 0.0}


def test_debt_setup_can_enter_a_promo_rate(monkeypatch, tmp_path):
    debt_path = setup_fixture_db(monkeypatch, tmp_path)

    responses = iter([
        "22.44", "25.0",  # auto-detected Fake Card's normal APR + min payment
        "y", "0", "2028-01-28",  # yes, on a promo: 0% until that date
        "n",  # no manual debts
    ])
    monkeypatch.setattr("builtins.input", lambda *_: next(responses))

    cli.cmd_debt(SimpleNamespace(debt_action="setup"))

    from money.debt import load_debts

    debts = load_debts(debt_path)
    assert debts["Fake Card"] == {
        "balance": 500.0, "apr": 22.44, "min_payment": 25.0,
        "promo_apr": 0.0, "promo_until": "2028-01-28",
    }


def test_debt_setup_reruns_keep_existing_promo_on_blank_answer(monkeypatch, tmp_path):
    debt_path = setup_fixture_db(monkeypatch, tmp_path)
    from money.debt import load_debts, save_debts

    save_debts(debt_path, {
        "Fake Card": {"balance": 500.0, "apr": 22.44, "min_payment": 25.0,
                      "promo_apr": 0.0, "promo_until": "2028-01-28"},
    })

    # Re-running setup: accept the existing APR/min payment (blank), and
    # leave the promo question blank too -> should keep the saved promo.
    responses = iter(["", "", "", "n"])
    monkeypatch.setattr("builtins.input", lambda *_: next(responses))

    cli.cmd_debt(SimpleNamespace(debt_action="setup"))

    debts = load_debts(debt_path)
    assert debts["Fake Card"]["promo_apr"] == 0.0
    assert debts["Fake Card"]["promo_until"] == "2028-01-28"


def test_debt_show_with_no_saved_debts(monkeypatch, tmp_path, capsys):
    setup_fixture_db(monkeypatch, tmp_path)

    cli.cmd_debt(SimpleNamespace(debt_action="show"))

    assert "No debts saved yet" in capsys.readouterr().out


def test_debt_show_after_setup(monkeypatch, tmp_path, capsys):
    setup_fixture_db(monkeypatch, tmp_path)
    responses = iter(["20.0", "25.0", "n", "n"])
    monkeypatch.setattr("builtins.input", lambda *_: next(responses))
    cli.cmd_debt(SimpleNamespace(debt_action="setup"))
    capsys.readouterr()

    cli.cmd_debt(SimpleNamespace(debt_action="show"))

    out = capsys.readouterr().out
    assert "Fake Card" in out
    assert "500.00" in out


def test_debt_plan_prints_payoff_timeline(monkeypatch, tmp_path, capsys):
    setup_fixture_db(monkeypatch, tmp_path)
    responses = iter(["20.0", "25.0", "n", "n"])
    monkeypatch.setattr("builtins.input", lambda *_: next(responses))
    cli.cmd_debt(SimpleNamespace(debt_action="setup"))
    capsys.readouterr()

    cli.cmd_debt(SimpleNamespace(debt_action="plan", extra=50.0))

    out = capsys.readouterr().out
    assert "Fake Card" in out
    assert "Debt-free in" in out


def test_debt_plan_with_no_saved_debts(monkeypatch, tmp_path, capsys):
    setup_fixture_db(monkeypatch, tmp_path)

    cli.cmd_debt(SimpleNamespace(debt_action="plan", extra=50.0))

    assert "No debts saved yet" in capsys.readouterr().out


def test_debt_plan_reports_when_budget_never_catches_up(monkeypatch, tmp_path, capsys):
    debt_path = setup_fixture_db(monkeypatch, tmp_path)
    from money.debt import save_debts

    save_debts(debt_path, {"Fake Card": {"balance": 10000.0, "apr": 30.0, "min_payment": 10.0}})

    cli.cmd_debt(SimpleNamespace(debt_action="plan", extra=0.0))

    out = capsys.readouterr().out
    assert "doesn't even cover the interest" in out
