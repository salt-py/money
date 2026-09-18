"""Discretionary income: what's left after income minus Non-Discretionary
spend minus your debt commitment (minimum payments from config/debt.yaml,
plus any planned avalanche "extra"), compared against what you actually
spent under Discretionary.

Which bucket a category falls into is config/categories.yaml's `parent`
chain -- not a separate config file, so the taxonomy has one source of
truth. Categories can nest more than one level deep (e.g. "Energy" ->
parent "Bills & Utilities" -> parent "Non-Discretionary"), so
classification walks up the chain rather than checking only the direct
parent. A category can also be left unclassified (no ancestor resolves to
either root) when it isn't real spend either way -- see the comments in
categories.yaml for why Income, Credit Card Payment, Credit Line Payment,
Interest, Transfers, and Uncategorized are all left that way -- those are
excluded from both totals and, for Uncategorized specifically, reported
separately since it might turn out to be either.
"""

from __future__ import annotations

from sqlite3 import Connection

DISCRETIONARY = "Discretionary"
NON_DISCRETIONARY = "Non-Discretionary"
_MAX_DEPTH = 10  # guards against an accidental cycle in categories.yaml


def _load_parent_map(conn: Connection) -> dict[str, str | None]:
    return {row["name"]: row["parent"] for row in conn.execute("SELECT name, parent FROM categories")}


def resolve_bucket(category: str, parent_map: dict[str, str | None]) -> str | None:
    """Walks up the parent chain from `category` until it hits
    "Discretionary", "Non-Discretionary", or a dead end (unknown category,
    no parent, or a cycle) -- returns None for a dead end.
    """
    seen = set()
    current = category
    for _ in range(_MAX_DEPTH):
        if current in (DISCRETIONARY, NON_DISCRETIONARY):
            return current
        if current in seen or current not in parent_map:
            return None
        seen.add(current)
        parent = parent_map[current]
        if not parent:
            return None
        current = parent
    return None  # chain too deep -- treat as a cycle rather than loop forever


def _category_totals(conn: Connection, month: str) -> list[dict]:
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
    return [dict(row) for row in rows]


def compute_discretionary(
    conn: Connection,
    month: str,
    debt_minimum_total: float = 0.0,
    debt_extra: float = 0.0,
) -> dict:
    totals = _category_totals(conn, month)
    parent_map = _load_parent_map(conn)

    income = 0.0
    essential_breakdown: dict[str, float] = {}
    discretionary_breakdown: dict[str, float] = {}
    uncategorized_net = 0.0

    for row in totals:
        category = row["category"]
        net = row["money_out"] - row["money_in"]
        if category == "Income":
            income = row["money_in"]
        elif category == "Uncategorized":
            uncategorized_net = net
        else:
            bucket = resolve_bucket(category, parent_map)
            if bucket == NON_DISCRETIONARY:
                essential_breakdown[category] = net
            elif bucket == DISCRETIONARY:
                discretionary_breakdown[category] = net
            # else: unclassified -- not counted in either total, e.g.
            # Transfers/Credit Card Payment/Credit Line Payment/Interest.

    essential_total = sum(essential_breakdown.values())
    discretionary_total = sum(discretionary_breakdown.values())
    discretionary_available = income - essential_total - debt_minimum_total - debt_extra

    return {
        "income": income,
        "essential_breakdown": essential_breakdown,
        "essential_total": essential_total,
        "debt_minimum_total": debt_minimum_total,
        "debt_extra": debt_extra,
        "discretionary_available": discretionary_available,
        "discretionary_breakdown": discretionary_breakdown,
        "discretionary_total": discretionary_total,
        "uncategorized_net": uncategorized_net,
        "surplus": discretionary_available - discretionary_total,
    }
