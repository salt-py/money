"""Integration test for `money categorize`'s interactive loop, driven with
scripted input against a synthetic DB -- never real data.
"""

from money import cli
from money.db import get_or_create_account, init_db, upsert_transaction


def setup_fixture_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    categories_path = tmp_path / "categories.yaml"
    rules_path = tmp_path / "rules.yaml"
    categories_path.write_text("categories:\n  - name: Uncategorized\n    parent: null\n  - name: Shopping\n    parent: null\n")
    rules_path.write_text("rules: []\n")

    monkeypatch.setattr(cli, "DB_PATH", db_path)
    monkeypatch.setattr(cli, "CATEGORIES_CONFIG", categories_path)
    monkeypatch.setattr(cli, "RULES_CONFIG", rules_path)

    conn = cli._open_db()
    account_id = get_or_create_account(conn, "FakeBank", "current", "Main")
    upsert_transaction(conn, account_id, "2026-08-01", -10.0, "FAKE SHOP LTD", None, "Uncategorized", "test", "e1")
    upsert_transaction(conn, account_id, "2026-08-05", -15.0, "FAKE SHOP LTD", None, "Uncategorized", "test", "e2")
    conn.commit()
    conn.close()
    return rules_path


def test_categorize_applies_chosen_category_and_saves_rule(monkeypatch, tmp_path, capsys):
    rules_path = setup_fixture_db(monkeypatch, tmp_path)

    # Categories seeded: [Shopping, Uncategorized] (alphabetical) -> "1" picks Shopping.
    # Then decline saving a rule.
    responses = iter(["1", "n"])
    monkeypatch.setattr("builtins.input", lambda *_: next(responses))

    cli.cmd_categorize(argparse_namespace())

    conn = cli._open_db()
    rows = conn.execute("SELECT category FROM transactions WHERE description = 'FAKE SHOP LTD'").fetchall()
    assert all(r["category"] == "Shopping" for r in rows)
    out = capsys.readouterr().out.lower()
    assert "rule added" not in out
    assert "[main]" in out  # account name shown alongside the group
    assert "rules: []" in rules_path.read_text()  # unchanged, since we declined


def test_categorize_can_save_a_rule(monkeypatch, tmp_path, capsys):
    rules_path = setup_fixture_db(monkeypatch, tmp_path)

    # Pick Shopping (1), agree to save a rule (y), accept the default
    # pattern (empty input), decline a friendly label (empty input).
    responses = iter(["1", "y", "", ""])
    monkeypatch.setattr("builtins.input", lambda *_: next(responses))

    cli.cmd_categorize(argparse_namespace())

    text = rules_path.read_text()
    assert "FAKE SHOP LTD".lower() in text.lower() or "fake\\ shop\\ ltd" in text.lower()
    assert "label:" not in text  # declined, so no label key written
    assert "Shopping" in text


def test_categorize_can_save_a_rule_with_a_friendly_label(monkeypatch, tmp_path):
    rules_path = setup_fixture_db(monkeypatch, tmp_path)

    responses = iter(["1", "y", "", "Some Shop Ltd"])
    monkeypatch.setattr("builtins.input", lambda *_: next(responses))

    cli.cmd_categorize(argparse_namespace())

    text = rules_path.read_text()
    assert "label: Some Shop Ltd" in text


def test_categorize_new_category_asks_for_discretionary_bucket(monkeypatch, tmp_path):
    rules_path = setup_fixture_db(monkeypatch, tmp_path)

    # "n" for new category, name it, "d" for Discretionary, decline rule.
    responses = iter(["n", "Fun Money", "d", "n"])
    monkeypatch.setattr("builtins.input", lambda *_: next(responses))

    cli.cmd_categorize(argparse_namespace())

    conn = cli._open_db()
    row = conn.execute("SELECT parent FROM categories WHERE name = 'Fun Money'").fetchone()
    assert row["parent"] == "Discretionary"

    import yaml

    categories_path = cli.CATEGORIES_CONFIG
    yaml_categories = yaml.safe_load(categories_path.read_text())["categories"]
    fun_money = next(c for c in yaml_categories if c["name"] == "Fun Money")
    assert fun_money["parent"] == "Discretionary"


def test_categorize_new_category_blank_bucket_stays_unclassified(monkeypatch, tmp_path):
    setup_fixture_db(monkeypatch, tmp_path)

    responses = iter(["n", "Reimbursements", "", "n"])
    monkeypatch.setattr("builtins.input", lambda *_: next(responses))

    cli.cmd_categorize(argparse_namespace())

    conn = cli._open_db()
    row = conn.execute("SELECT parent FROM categories WHERE name = 'Reimbursements'").fetchone()
    assert row["parent"] is None


def test_categorize_no_uncategorized_transactions_prints_message(monkeypatch, tmp_path, capsys):
    db_path = tmp_path / "empty.db"
    categories_path = tmp_path / "categories.yaml"
    categories_path.write_text("categories:\n  - name: Uncategorized\n    parent: null\n")
    monkeypatch.setattr(cli, "DB_PATH", db_path)
    monkeypatch.setattr(cli, "CATEGORIES_CONFIG", categories_path)

    cli.cmd_categorize(argparse_namespace())

    assert "No uncategorized transactions." in capsys.readouterr().out


def argparse_namespace():
    class NS:
        pass

    return NS()
