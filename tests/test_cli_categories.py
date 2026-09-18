"""Integration test for `money categories`, driven against synthetic
data -- structure only, but keeping with the pattern used elsewhere.
"""

from types import SimpleNamespace

import yaml

from money import cli


def setup_fixture(monkeypatch, tmp_path, categories_yaml, rules_yaml="rules: []\n"):
    db_path = tmp_path / "test.db"
    categories_path = tmp_path / "categories.yaml"
    rules_path = tmp_path / "rules.yaml"
    categories_path.write_text(categories_yaml)
    rules_path.write_text(rules_yaml)

    monkeypatch.setattr(cli, "DB_PATH", db_path)
    monkeypatch.setattr(cli, "CATEGORIES_CONFIG", categories_path)
    monkeypatch.setattr(cli, "RULES_CONFIG", rules_path)


def run_categories(monkeypatch, capsys, category=None):
    cli.cmd_categories(SimpleNamespace(category=category))
    return yaml.safe_load(capsys.readouterr().out)


def test_categories_prints_tree_structure(monkeypatch, tmp_path, capsys):
    setup_fixture(
        monkeypatch,
        tmp_path,
        "categories:\n"
        "  - name: Discretionary\n    parent: null\n"
        "  - name: Non-Discretionary\n    parent: null\n"
        "  - name: Bills & Utilities\n    parent: Non-Discretionary\n"
        "  - name: Utilities\n    parent: Bills & Utilities\n"
        "  - name: Shopping\n    parent: Discretionary\n"
        "  - name: Income\n    parent: null\n",
    )

    tree = run_categories(monkeypatch, capsys)

    assert tree == {
        "Discretionary": {"Shopping": {}},
        "Income": {},
        "Non-Discretionary": {"Bills & Utilities": {"Utilities": {}}},
    }


def test_categories_shows_rules_nested_under_their_category(monkeypatch, tmp_path, capsys):
    setup_fixture(
        monkeypatch,
        tmp_path,
        "categories:\n"
        "  - name: Discretionary\n    parent: null\n"
        "  - name: Shopping\n    parent: Discretionary\n",
        rules_yaml=(
            "rules:\n"
            "  - pattern: amazon\n    category: Shopping\n"
            "  - pattern: argos\n    category: Shopping\n"
        ),
    )

    tree = run_categories(monkeypatch, capsys)

    assert tree == {
        "Discretionary": {"Shopping": {"rules": ["amazon", "argos"]}},
    }


def test_categories_shows_label_instead_of_pattern_when_set(monkeypatch, tmp_path, capsys):
    setup_fixture(
        monkeypatch,
        tmp_path,
        "categories:\n"
        "  - name: Discretionary\n    parent: null\n"
        "  - name: Shopping\n    parent: Discretionary\n",
        rules_yaml=(
            "rules:\n"
            "  - pattern: MERCHANT123\n    category: Shopping\n    label: Some cryptic merchant code\n"
        ),
    )

    tree = run_categories(monkeypatch, capsys)

    assert tree == {
        "Discretionary": {"Shopping": {"rules": ["Some cryptic merchant code"]}},
    }


def test_categories_shows_env_rules_by_name_not_value(monkeypatch, tmp_path, capsys):
    setup_fixture(
        monkeypatch,
        tmp_path,
        "categories:\n"
        "  - name: Non-Discretionary\n    parent: null\n"
        "  - name: Household Contribution\n    parent: Non-Discretionary\n",
    )

    out = run_categories(monkeypatch, capsys)

    rules = out["Non-Discretionary"]["Household Contribution"]["rules"]
    assert any("HOUSEHOLD_ACCOUNT_REF" in r and "value not shown" in r for r in rules)


def test_categories_with_argument_prints_only_that_subtree(monkeypatch, tmp_path, capsys):
    setup_fixture(
        monkeypatch,
        tmp_path,
        "categories:\n"
        "  - name: Discretionary\n    parent: null\n"
        "  - name: Shopping\n    parent: Discretionary\n"
        "  - name: Income\n    parent: null\n",
        rules_yaml="rules:\n  - pattern: amazon\n    category: Shopping\n",
    )

    tree = run_categories(monkeypatch, capsys, category="Discretionary")

    assert tree == {"Discretionary": {"Shopping": {"rules": ["amazon"]}}}


def test_categories_with_unknown_argument_prints_a_message(monkeypatch, tmp_path, capsys):
    setup_fixture(
        monkeypatch,
        tmp_path,
        "categories:\n  - name: Income\n    parent: null\n",
    )

    cli.cmd_categories(SimpleNamespace(category="No Such Category"))

    assert "No such category" in capsys.readouterr().out
