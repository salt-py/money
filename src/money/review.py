"""Core logic for the interactive `money categorize` review tool (see
cli.py's cmd_categorize for the actual terminal loop). Split out so it's
unit-testable against synthetic data -- this module itself never prints
anything or touches real data on its own.
"""

from __future__ import annotations

import re
from pathlib import Path
from sqlite3 import Connection

import yaml

UNCATEGORIZED = "Uncategorized"


def _append_yaml_list_entry(path: Path, key: str, entry: dict) -> None:
    """Appends one entry to a top-level YAML list (config/categories.yaml's
    `categories:` or config/rules.yaml's `rules:`), as raw text rather than
    a full parse+dump, to avoid clobbering existing comments/formatting.

    Handles the list currently being empty in flow style (`key: []`) --
    block-style items (`  - ...`) can't just be appended below that as-is,
    since mixing the two forms for the same key isn't valid YAML.
    """
    content = path.read_text()
    empty_flow_list = re.compile(rf"^{re.escape(key)}:\s*\[\s*\]\s*$", re.MULTILINE)
    if empty_flow_list.search(content):
        content = empty_flow_list.sub(f"{key}:", content)
        path.write_text(content)

    entry_yaml = yaml.safe_dump([entry], default_flow_style=False, sort_keys=False)
    indented = "\n".join(("  " + line if line.strip() else line) for line in entry_yaml.splitlines())
    with path.open("a") as f:
        f.write("\n" + indented + "\n")


def list_uncategorized_groups(conn: Connection) -> list[dict]:
    """Groups uncategorized transactions by their exact description, since
    a recurring payee usually reuses the same description verbatim.
    Ordered by total absolute amount descending, so financially
    significant groups get triaged first.

    `accounts` is every distinct account name this description showed up
    on (comma-separated) -- usually just one, but worth surfacing since
    the same payee can appear on more than one account/card, and knowing
    which account a transaction is on is often the context needed to
    categorize it correctly.
    """
    rows = conn.execute(
        """
        SELECT t.description, COUNT(*) AS n, SUM(t.amount) AS total,
               MIN(t.date) AS min_date, MAX(t.date) AS max_date,
               GROUP_CONCAT(DISTINCT a.name) AS accounts
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        WHERE t.category = ?
        GROUP BY t.description
        ORDER BY ABS(SUM(t.amount)) DESC
        """,
        (UNCATEGORIZED,),
    ).fetchall()
    return [dict(row) for row in rows]


def set_category_for_description(conn: Connection, description: str, category: str) -> int:
    """Updates every currently-Uncategorized transaction with this exact
    description. Scoped to Uncategorized only, so this never overwrites a
    category set some other way (a rule, a previous manual pass).
    Returns the number of rows updated.
    """
    cur = conn.execute(
        "UPDATE transactions SET category = ? WHERE description = ? AND category = ?",
        (category, description, UNCATEGORIZED),
    )
    conn.commit()
    return cur.rowcount


def add_category(categories_path: Path, conn: Connection, name: str, parent: str | None = None) -> None:
    """Adds a new category to both the live DB (so it's usable this
    session) and config/categories.yaml (so it survives a fresh init-db,
    and is visible to anyone reading the config). Appended as raw text
    rather than a full parse+dump, to avoid clobbering existing comments
    and formatting in the yaml file.

    `parent` should normally be "Discretionary" or "Non-Discretionary" (see
    money/discretionary.py) so the new category isn't silently excluded
    from `report discretionary` -- but left optional, since a handful of
    categories are deliberately unclassified (Income, Transfers, ...).
    """
    conn.execute("INSERT OR IGNORE INTO categories (name, parent) VALUES (?, ?)", (name, parent))
    conn.commit()

    existing = yaml.safe_load(categories_path.read_text()) or {}
    if any(c["name"] == name for c in existing.get("categories", [])):
        return

    _append_yaml_list_entry(categories_path, "categories", {"name": name, "parent": parent})


def add_rule(rules_path: Path, pattern: str, category: str, label: str | None = None) -> None:
    """Appends a new categorization rule to config/rules.yaml, as raw text
    rather than a full parse+dump (same reasoning as add_category). New
    rules are appended at the end, so they're checked *after* everything
    already there -- existing more-specific rules still win first-match.

    `label` is an optional human-readable name for a cryptic pattern (e.g.
    a reference-number-prefixed merchant string), shown by
    `money categories` alongside the raw pattern.
    """
    entry = {"pattern": pattern, "category": category}
    if label:
        entry["label"] = label
    _append_yaml_list_entry(rules_path, "rules", entry)
