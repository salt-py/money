"""Reports print straight to your terminal (or redirect to a file yourself,
e.g. `python -m money.cli report spending --month 2026-08 > reports/aug.txt`)
-- nothing here is ever captured by an AI tool call.
"""

from __future__ import annotations

from sqlite3 import Connection


def net_worth(conn: Connection, since: str | None = None) -> None:
    rows = conn.execute(
        """
        SELECT a.name, b.balance, b.snapshot_date
        FROM balances b
        JOIN accounts a ON a.id = b.account_id
        WHERE b.snapshot_date = (
            SELECT MAX(snapshot_date) FROM balances b2 WHERE b2.account_id = b.account_id
        )
        ORDER BY a.name
        """
    ).fetchall()

    print("Latest balance per account:")
    total = 0.0
    for row in rows:
        print(f"  {row['name']:30s} {row['balance']:>12.2f}  (as of {row['snapshot_date']})")
        total += row["balance"]
    print(f"  {'TOTAL':30s} {total:>12.2f}")

    if since:
        print(f"\nTotal balance by snapshot date since {since}:")
        trend = conn.execute(
            """
            SELECT snapshot_date, SUM(balance) AS total
            FROM balances
            WHERE snapshot_date >= ?
            GROUP BY snapshot_date
            ORDER BY snapshot_date
            """,
            (since,),
        ).fetchall()
        for row in trend:
            print(f"  {row['snapshot_date']}  {row['total']:>12.2f}")
        print(
            "  (note: a date's total only reflects accounts that were "
            "imported on that date -- run imports for all accounts on the "
            "same day for a true point-in-time trend)"
        )


def spending(conn: Connection, month: str, by: str = "category") -> None:
    rows = conn.execute(
        """
        SELECT category, SUM(-amount) AS total, COUNT(*) AS n
        FROM transactions
        WHERE date LIKE ? AND amount < 0
        GROUP BY category
        ORDER BY total DESC
        """,
        (f"{month}%",),
    ).fetchall()

    if not rows:
        print(f"No spending recorded for {month}.")
        return

    print(f"Spending by category for {month}:")
    grand_total = 0.0
    for row in rows:
        print(f"  {row['category']:25s} {row['total']:>10.2f}  ({row['n']} txns)")
        grand_total += row["total"]
    print(f"  {'TOTAL':25s} {grand_total:>10.2f}")


def household(conn: Connection, month: str) -> None:
    def category_total(category: str) -> float:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(-amount), 0) AS total
            FROM transactions
            WHERE date LIKE ? AND category = ? AND amount < 0
            """,
            (f"{month}%", category),
        ).fetchone()
        return row["total"]

    def income_total() -> float:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM transactions
            WHERE date LIKE ? AND category = 'Income' AND amount > 0
            """,
            (f"{month}%",),
        ).fetchone()
        return row["total"]

    contribution = category_total("Household Contribution")
    income = income_total()

    print(f"Household contribution for {month}: {contribution:.2f}")
    if income > 0:
        pct = contribution / income * 100
        print(f"Income this month: {income:.2f}  ({pct:.1f}% sent to household)")
    else:
        print("No income recorded this month -- can't compute a percentage.")


def budget_vs_actual(conn: Connection, month: str, budget: dict[str, float]) -> None:
    """Money out and money in are shown as separate columns per category,
    not netted into one number -- a category with both a purchase and a
    refund (or an Uncategorized bucket mixing real spend with unrelated
    incoming transfers) would otherwise hide one side of that.
    `net` (out - in) is what's compared against the budgeted amount.
    """
    if not budget:
        print("No budget saved yet -- run `python -m money.cli budget suggest --save` first.")
        return

    rows = conn.execute(
        """
        SELECT category,
               SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END) AS money_out,
               SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS money_in
        FROM transactions
        WHERE date LIKE ?
        GROUP BY category
        """,
        (f"{month}%",),
    ).fetchall()
    actual = {row["category"]: (row["money_out"], row["money_in"]) for row in rows}

    categories = sorted(set(budget) | set(actual))
    print(f"Budget vs actual for {month}:")
    print(f"  {'Category':25s} {'budget':>9s} {'out':>9s} {'in':>9s} {'net':>9s} {'variance':>9s}")
    total_budget = total_out = total_in = 0.0
    for category in categories:
        budgeted = budget.get(category, 0.0)
        money_out, money_in = actual.get(category, (0.0, 0.0))
        net = money_out - money_in
        variance = budgeted - net
        flag = "  OVER" if variance < 0 else ""
        print(
            f"  {category:25s} {budgeted:>9.2f} {money_out:>9.2f} {money_in:>9.2f} "
            f"{net:>9.2f} {variance:>9.2f}{flag}"
        )
        total_budget += budgeted
        total_out += money_out
        total_in += money_in
    total_net = total_out - total_in
    print(
        f"  {'TOTAL':25s} {total_budget:>9.2f} {total_out:>9.2f} {total_in:>9.2f} "
        f"{total_net:>9.2f} {total_budget - total_net:>9.2f}"
    )


def discretionary(
    conn: Connection,
    month: str,
    debt_minimum_total: float = 0.0,
    debt_extra: float = 0.0,
) -> None:
    from money.discretionary import compute_discretionary

    result = compute_discretionary(conn, month, debt_minimum_total, debt_extra)

    print(f"Discretionary income for {month}:\n")
    print(f"  Income                          {result['income']:>10.2f}")
    print("  Non-Discretionary:")
    for cat, net in sorted(result["essential_breakdown"].items()):
        print(f"    {cat:25s}      -{net:>10.2f}")
    print(f"    {'(subtotal)':25s}      -{result['essential_total']:>10.2f}")
    if debt_minimum_total or debt_extra:
        print(f"  Debt minimum payments            -{debt_minimum_total:>10.2f}")
        if debt_extra:
            print(f"  Debt extra (planned)             -{debt_extra:>10.2f}")
    print(f"  {'Available for discretionary spend':33s} {result['discretionary_available']:>10.2f}\n")

    print("  Actual discretionary spend by category:")
    if not result["discretionary_breakdown"]:
        print("    (none)")
    for cat, net in sorted(result["discretionary_breakdown"].items(), key=lambda kv: -kv[1]):
        print(f"    {cat:25s}       {net:>10.2f}")
    print(f"    {'(subtotal)':25s}       {result['discretionary_total']:>10.2f}")

    if result["uncategorized_net"]:
        print(
            f"\n  Uncategorized (not counted above, could be essential or "
            f"discretionary): {result['uncategorized_net']:.2f}"
        )

    flag = "  UNDER (overspent)" if result["surplus"] < 0 else "  spare"
    print(f"\n  Surplus vs available: {result['surplus']:>10.2f}{flag}")
