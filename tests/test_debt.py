from datetime import date

import pytest

from money.db import get_connection, get_or_create_account, init_db, record_balance
from money.debt import (
    _add_months,
    effective_apr,
    get_tracked_debt_accounts,
    load_debts,
    save_debts,
    simulate_avalanche,
)


def test_add_months_same_year():
    assert _add_months(date(2026, 9, 15), 3) == date(2026, 12, 1)


def test_add_months_crosses_year_boundary():
    assert _add_months(date(2026, 11, 1), 3) == date(2027, 2, 1)


def test_get_tracked_debt_accounts_only_negative_balances(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    debt_acc = get_or_create_account(conn, "FakeCard", "credit_card", "Fake Card")
    asset_acc = get_or_create_account(conn, "FakeBank", "current", "Fake Current")
    record_balance(conn, debt_acc, "2026-09-01", -500.0)
    record_balance(conn, asset_acc, "2026-09-01", 1200.0)
    conn.commit()

    debts = get_tracked_debt_accounts(conn)
    assert len(debts) == 1
    assert debts[0] == {"name": "Fake Card", "balance": 500.0}


def test_get_tracked_debt_accounts_uses_latest_snapshot(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    acc = get_or_create_account(conn, "FakeCard", "credit_card", "Fake Card")
    record_balance(conn, acc, "2026-08-01", -900.0)
    record_balance(conn, acc, "2026-09-01", -500.0)
    conn.commit()

    debts = get_tracked_debt_accounts(conn)
    assert debts == [{"name": "Fake Card", "balance": 500.0}]


def test_load_debts_missing_file_returns_empty(tmp_path):
    assert load_debts(tmp_path / "nonexistent.yaml") == {}


def test_save_and_load_debts_round_trip(tmp_path):
    path = tmp_path / "debt.yaml"
    save_debts(path, {"Fake Card": {"balance": 500.1234, "apr": 22.4, "min_payment": 25.0}})

    loaded = load_debts(path)
    assert loaded == {"Fake Card": {"balance": 500.12, "apr": 22.4, "min_payment": 25.0}}
    assert path.read_text().startswith("#")


def test_simulate_avalanche_zero_interest_pays_off_in_exact_months():
    debts = {"Fake Card": {"balance": 1200.0, "apr": 0.0, "min_payment": 100.0}}
    result = simulate_avalanche(debts, extra_monthly=0.0, as_of=date(2026, 9, 1))
    assert result["months"] == 12
    assert result["total_interest"] == 0.0
    assert result["payoff_order"][0]["payoff_month"] == 12
    assert result["payoff_order"][0]["payoff_date"] == "2027-09-01"


def test_simulate_avalanche_matches_hand_calculated_interest():
    # See docstring math: month 1 accrues £10 interest (1000 * 1%), pays
    # off £1000 of the resulting £1010, leaving £10; month 2 accrues 10c,
    # then pays off the remaining £10.10.
    debts = {"Fake Card": {"balance": 1000.0, "apr": 12.0, "min_payment": 1000.0}}
    result = simulate_avalanche(debts, extra_monthly=0.0, as_of=date(2026, 9, 1))
    assert result["months"] == 2
    assert result["total_interest"] == pytest.approx(10.1, abs=0.01)


def test_simulate_avalanche_targets_highest_apr_first():
    debts = {
        "Low APR": {"balance": 500.0, "apr": 10.0, "min_payment": 50.0},
        "High APR": {"balance": 500.0, "apr": 20.0, "min_payment": 50.0},
    }
    result = simulate_avalanche(debts, extra_monthly=100.0, as_of=date(2026, 9, 1))
    order_names = [d["name"] for d in result["payoff_order"]]
    assert order_names == ["High APR", "Low APR"]
    high, low = result["payoff_order"]
    assert high["payoff_month"] <= low["payoff_month"]


def test_simulate_avalanche_returns_none_when_budget_never_catches_up():
    debts = {"Fake Card": {"balance": 10000.0, "apr": 30.0, "min_payment": 10.0}}
    result = simulate_avalanche(debts, extra_monthly=0.0, as_of=date(2026, 9, 1), max_months=12)
    assert result["months"] is None
    assert result["total_interest"] is None


def test_effective_apr_before_promo_end_uses_promo_rate():
    debt = {"apr": 30.0, "promo_apr": 0.0, "promo_until": "2027-01-01"}
    assert effective_apr(debt, date(2026, 9, 1)) == 0.0


def test_effective_apr_on_or_after_promo_end_uses_normal_rate():
    debt = {"apr": 30.0, "promo_apr": 0.0, "promo_until": "2027-01-01"}
    assert effective_apr(debt, date(2027, 1, 1)) == 30.0
    assert effective_apr(debt, date(2027, 6, 1)) == 30.0


def test_effective_apr_without_promo_fields_returns_apr():
    assert effective_apr({"apr": 22.4}, date(2026, 9, 1)) == 22.4


def test_save_and_load_debts_with_promo_round_trip(tmp_path):
    path = tmp_path / "debt.yaml"
    save_debts(
        path,
        {"Promo Card": {"balance": 1000.0, "apr": 26.4, "min_payment": 25.0, "promo_apr": 0.0, "promo_until": "2027-03-01"}},
    )
    loaded = load_debts(path)
    assert loaded["Promo Card"]["promo_apr"] == 0.0
    assert loaded["Promo Card"]["promo_until"] == "2027-03-01"


def test_save_debts_omits_promo_fields_when_not_set(tmp_path):
    path = tmp_path / "debt.yaml"
    save_debts(path, {"Fake Card": {"balance": 500.0, "apr": 22.4, "min_payment": 25.0}})
    text = path.read_text()
    # Only checking for the YAML keys themselves (with a colon) -- the
    # header comment mentions promo_apr/promo_until in prose regardless.
    assert "promo_apr:" not in text
    assert "promo_until:" not in text


def test_simulate_avalanche_promo_rate_deprioritizes_extra_payments():
    # Card A is on a (long-lasting) 0% promo -- its real APR is higher
    # than Card B's, but while the promo is active it should NOT get
    # targeted ahead of B for the "extra" payment.
    debts = {
        "Card A": {
            "balance": 500.0, "apr": 30.0, "min_payment": 10.0,
            "promo_apr": 0.0, "promo_until": "2099-01-01",
        },
        "Card B": {"balance": 500.0, "apr": 15.0, "min_payment": 10.0},
    }
    result = simulate_avalanche(debts, extra_monthly=100.0, as_of=date(2026, 9, 1))
    assert result["payoff_order"][0]["name"] == "Card B"


def test_simulate_avalanche_promo_ending_shifts_priority_to_that_debt():
    # Same shape, but Card A's promo ends after month 1 -- once it reverts
    # to its higher real APR, the avalanche should redirect extra payments
    # to it, and it should end up paid off well before Card B despite the
    # one-month head start disadvantage.
    debts = {
        "Card A": {
            "balance": 500.0, "apr": 30.0, "min_payment": 10.0,
            "promo_apr": 0.0, "promo_until": "2026-10-01",
        },
        "Card B": {"balance": 500.0, "apr": 15.0, "min_payment": 10.0},
    }
    result = simulate_avalanche(debts, extra_monthly=100.0, as_of=date(2026, 9, 1))
    a = next(d for d in result["payoff_order"] if d["name"] == "Card A")
    b = next(d for d in result["payoff_order"] if d["name"] == "Card B")
    assert a["payoff_month"] < b["payoff_month"]
