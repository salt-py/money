"""Rule-based transaction categorization.

Rules are checked in order; the first matching pattern wins. Anything that
matches nothing falls back to "Uncategorized" so you can review it later
with a report and tighten config/rules.yaml.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

UNCATEGORIZED = "Uncategorized"

# Environment variable -> category, for rules that reference a real,
# identifying value (e.g. an account number). rules.yaml is gitignored like
# .env, but it's the kind of file you might paste somewhere to debug a
# categorization issue -- .env never should be, so it's the safer home for
# these. Comma-separate multiple values in one var to match any of them
# (e.g. HOUSEHOLD_ACCOUNT_REF="45985049,some other reference").
ENV_RULE_CATEGORIES = {
    "HOUSEHOLD_ACCOUNT_REF": "Household Contribution",
}


@dataclass
class Rule:
    pattern: re.Pattern
    category: str
    label: str | None = None  # human-readable name, e.g. for a cryptic pattern


def load_rules(rules_path: Path) -> list[Rule]:
    data = yaml.safe_load(rules_path.read_text()) or {}
    rules = []
    for entry in data.get("rules", []):
        rules.append(
            Rule(
                pattern=re.compile(entry["pattern"], re.IGNORECASE),
                category=entry["category"],
                label=entry.get("label"),
            )
        )
    return rules


def load_env_rules() -> list[Rule]:
    """Builds rules from environment variables rather than the git-tracked
    config/rules.yaml -- for patterns built around a real, identifying
    value (a joint/household account number, say) that you don't want
    permanently baked into git history. Returns [] for any var that isn't
    set in .env, so this is a no-op until you opt in.
    """
    rules = []
    for env_var, category in ENV_RULE_CATEGORIES.items():
        raw = os.environ.get(env_var)
        if not raw:
            continue
        values = [v.strip() for v in raw.split(",") if v.strip()]
        if not values:
            continue
        pattern = "|".join(re.escape(v) for v in values)
        rules.append(Rule(pattern=re.compile(pattern, re.IGNORECASE), category=category))
    return rules


def categorize(description: str, merchant: str | None, rules: list[Rule]) -> str:
    haystack = f"{description} {merchant or ''}"
    for rule in rules:
        if rule.pattern.search(haystack):
            return rule.category
    return UNCATEGORIZED
