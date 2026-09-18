import re

from money.categorize import Rule, categorize, load_env_rules, load_rules


def make_rules():
    return [
        Rule(pattern=re.compile("tesco|sainsbury", re.IGNORECASE), category="Groceries"),
        Rule(pattern=re.compile("salary", re.IGNORECASE), category="Income"),
    ]


def test_matches_first_rule():
    rules = make_rules()
    assert categorize("TESCO STORES 1234", None, rules) == "Groceries"


def test_matches_against_merchant_too():
    rules = make_rules()
    assert categorize("Card payment", "Sainsbury's", rules) == "Groceries"


def test_falls_back_to_uncategorized():
    rules = make_rules()
    assert categorize("Some random shop", None, rules) == "Uncategorized"


def test_case_insensitive():
    rules = make_rules()
    assert categorize("monthly SALARY payment", None, rules) == "Income"


def test_load_env_rules_empty_when_unset(monkeypatch):
    monkeypatch.delenv("HOUSEHOLD_ACCOUNT_REF", raising=False)
    assert load_env_rules() == []


def test_load_env_rules_builds_rule_from_env(monkeypatch):
    monkeypatch.setenv("HOUSEHOLD_ACCOUNT_REF", "12345678")
    rules = load_env_rules()
    assert len(rules) == 1
    assert rules[0].category == "Household Contribution"
    assert categorize("To A/C 12345678", None, rules) == "Household Contribution"
    assert categorize("Some other payee", None, rules) == "Uncategorized"


def test_load_env_rules_supports_comma_separated_values(monkeypatch):
    monkeypatch.setenv("HOUSEHOLD_ACCOUNT_REF", "12345678, wife name")
    rules = load_env_rules()
    assert categorize("TRANSFER wife name", None, rules) == "Household Contribution"
    assert categorize("To A/C 12345678", None, rules) == "Household Contribution"


def test_load_rules_reads_optional_label(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text(
        "rules:\n"
        "  - pattern: MERCHANT123\n"
        "    category: Household Contribution\n"
        "    label: Some cryptic merchant code\n"
        "  - pattern: tesco\n"
        "    category: Groceries\n"
    )
    rules = load_rules(path)
    assert rules[0].label == "Some cryptic merchant code"
    assert rules[1].label is None  # no label key -- defaults to None, not an error
