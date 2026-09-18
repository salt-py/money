"""Debt payoff planning: tracks per-debt balance/APR/minimum payment and
simulates an avalanche payoff (highest *effective* APR first --
mathematically minimizes total interest paid, which is what actually gets
you debt-free fastest for a given monthly budget).

Two ways a debt gets into config/debt.yaml (gitignored -- like
budget.yaml, this holds real balances and interest rates, not just
category names):

- Auto-detected: any account with a tracked negative balance in the
  `balances` table (credit cards imported via a PDF format with
  `balance_label_pattern` set, or Monzo if its live API balance ever goes
  negative). `money debt setup` lists these as a starting point.
- Manual: anything the app can't see automatically -- a NatWest overdraft,
  say, since that PDF export has no closing-balance summary field the way
  the credit card statements do. Added by hand in the same `setup` flow.

APR and minimum payment are always entered by hand either way -- neither
has ever been machine-extracted from a statement in this app, so there's
no meaningful difference in how "tracked" vs. "manual" debts are entered
beyond where the balance itself came from.

A debt can optionally carry a promotional rate (`promo_apr` lower than
`apr`, e.g. a 0% balance-transfer offer, active until `promo_until`) --
its *effective* rate is `promo_apr` before that date and `apr` from that
date on. Since a promo reverting can flip which debt has the highest rate
partway through a payoff, the avalanche target is recomputed every month
rather than fixed once upfront.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from sqlite3 import Connection

import yaml


def get_tracked_debt_accounts(conn: Connection) -> list[dict]:
    """Every account whose latest balance snapshot is negative (i.e. it's
    debt, not an asset) -- a starting point for `money debt setup`, not
    exhaustive (see module docstring re: manual entries).
    """
    rows = conn.execute(
        """
        SELECT a.name, b.balance
        FROM balances b
        JOIN accounts a ON a.id = b.account_id
        WHERE b.snapshot_date = (
            SELECT MAX(snapshot_date) FROM balances b2 WHERE b2.account_id = b.account_id
        )
        AND b.balance < 0
        ORDER BY b.balance ASC
        """
    ).fetchall()
    return [{"name": row["name"], "balance": -row["balance"]} for row in rows]


def load_debts(debt_path: Path) -> dict[str, dict]:
    if not debt_path.exists():
        return {}
    data = yaml.safe_load(debt_path.read_text()) or {}
    return dict(data.get("debts", {}))


def save_debts(debt_path: Path, debts: dict[str, dict]) -> None:
    debt_path.parent.mkdir(parents=True, exist_ok=True)
    saved = {}
    for name, d in sorted(debts.items()):
        entry = {
            "balance": round(d["balance"], 2),
            "apr": round(d["apr"], 3),
            "min_payment": round(d["min_payment"], 2),
        }
        if d.get("promo_apr") is not None and d.get("promo_until"):
            entry["promo_apr"] = round(d["promo_apr"], 3)
            entry["promo_until"] = d["promo_until"]
        saved[name] = entry
    body = {"debts": saved}
    header = (
        "# Debt payoff tracking: balance owed, annual interest rate (APR,\n"
        "# as a percentage e.g. 22.4 not 0.224), and minimum monthly\n"
        "# payment per debt. Optional promo_apr/promo_until model a\n"
        "# promotional rate (e.g. 0% balance transfer) that reverts to\n"
        "# `apr` on that date (YYYY-MM-DD).\n"
        "# Gitignored -- real financial figures, not just category names.\n"
        "# Generated/updated by `money debt setup`, or edit by hand.\n"
        "# Plan a payoff with:\n"
        "#   python -m money.cli debt plan --extra 200\n"
    )
    debt_path.write_text(header + yaml.safe_dump(body, default_flow_style=False, sort_keys=False))


def _add_months(d: date, months: int) -> date:
    month0 = d.month - 1 + months
    year = d.year + month0 // 12
    month = month0 % 12 + 1
    return date(year, month, 1)


def effective_apr(debt: dict, on_date: date) -> float:
    """The APR actually in effect on a given date -- `promo_apr` while
    before `promo_until`, otherwise the normal `apr`. A debt with no
    promo fields just always returns `apr`.
    """
    promo_until = debt.get("promo_until")
    if promo_until and debt.get("promo_apr") is not None:
        try:
            promo_end = date.fromisoformat(str(promo_until))
        except ValueError:
            return debt["apr"]
        if on_date < promo_end:
            return debt["promo_apr"]
    return debt["apr"]


def simulate_avalanche(
    debts: dict[str, dict], extra_monthly: float, as_of: date | None = None, max_months: int = 600
) -> dict:
    """Highest-*effective*-APR-first payoff simulation. Each month:
    interest accrues on every remaining balance at its effective rate for
    that month, minimum payments are made on every debt still owing, then
    whatever's left of the fixed monthly budget (sum of original minimums
    + extra_monthly) goes to whichever remaining debt currently has the
    highest effective APR. As each debt clears, its minimum is no longer
    subtracted, so the budget increasingly flows to the target -- the
    "avalanche" effect. The target is recomputed every month (not fixed
    upfront) since a promo rate reverting can change which debt has the
    highest rate partway through.

    Returns total months to debt-free, total interest paid, and a payoff
    month/date per debt, ordered by when each was actually paid off (the
    most intuitive order to display, since the avalanche target itself can
    change over time). If `max_months` is hit without reaching zero (the
    monthly budget doesn't even cover accruing interest), `months` is None
    to signal that rather than returning a misleadingly large number.
    """
    as_of = as_of or date.today()
    names = list(debts.keys())
    balances = {n: float(debts[n]["balance"]) for n in names}
    total_monthly_budget = sum(d["min_payment"] for d in debts.values()) + extra_monthly

    total_interest = 0.0
    payoff_month: dict[str, int] = {}
    month = 0
    converged = True
    while any(balances[n] > 0.01 for n in names):
        month += 1
        if month > max_months:
            converged = False
            break

        month_date = _add_months(as_of, month - 1)

        for n in names:
            if balances[n] > 0.01:
                apr = effective_apr(debts[n], month_date)
                interest = balances[n] * (apr / 100 / 12)
                balances[n] += interest
                total_interest += interest

        order = sorted(names, key=lambda n: -effective_apr(debts[n], month_date))

        budget = total_monthly_budget
        for n in order:
            if balances[n] <= 0.01:
                continue
            pay = min(debts[n]["min_payment"], balances[n], budget)
            balances[n] -= pay
            budget -= pay

        for n in order:
            if balances[n] <= 0.01 or budget <= 0:
                continue
            pay = min(budget, balances[n])
            balances[n] -= pay
            budget -= pay

        for n in order:
            if balances[n] <= 0.01 and n not in payoff_month:
                payoff_month[n] = month

    # Display order: the sequence debts actually got paid off in (or, for
    # a non-convergent run, the initial-month avalanche order as a
    # reasonable fallback).
    if converged:
        display_order = sorted(names, key=lambda n: payoff_month[n])
    else:
        display_order = sorted(names, key=lambda n: -effective_apr(debts[n], as_of))

    return {
        "months": month if converged else None,
        "total_interest": round(total_interest, 2) if converged else None,
        "payoff_order": [
            {
                "name": n,
                "balance": debts[n]["balance"],
                "apr": debts[n]["apr"],
                "min_payment": debts[n]["min_payment"],
                "promo_apr": debts[n].get("promo_apr"),
                "promo_until": debts[n].get("promo_until"),
                "payoff_month": payoff_month.get(n),
                "payoff_date": _add_months(as_of, payoff_month[n]).isoformat() if n in payoff_month else None,
            }
            for n in display_order
        ],
    }
