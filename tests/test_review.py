from money.db import get_connection, get_or_create_account, init_db, upsert_transaction
from money.review import add_category, add_rule, list_uncategorized_groups, set_category_for_description


def make_conn_with_fixture_txns(tmp_path, categories_config=None):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn, categories_config)
    account_id = get_or_create_account(conn, "FakeBank", "current", "Main")

    # Two transactions sharing a description (should group together), one
    # already categorized (should be excluded), one uniquely uncategorized.
    upsert_transaction(conn, account_id, "2026-08-01", -10.0, "FAKE SHOP LTD", None, "Uncategorized", "test", "e1")
    upsert_transaction(conn, account_id, "2026-08-05", -15.0, "FAKE SHOP LTD", None, "Uncategorized", "test", "e2")
    upsert_transaction(conn, account_id, "2026-08-02", -5.0, "ALREADY DONE", None, "Groceries", "test", "e3")
    upsert_transaction(conn, account_id, "2026-08-03", 100.0, "FAKE SALARY LTD", None, "Uncategorized", "test", "e4")
    conn.commit()
    return conn, account_id


def test_list_uncategorized_groups_excludes_already_categorized(tmp_path):
    conn, _ = make_conn_with_fixture_txns(tmp_path)
    groups = list_uncategorized_groups(conn)
    descriptions = {g["description"] for g in groups}
    assert descriptions == {"FAKE SHOP LTD", "FAKE SALARY LTD"}


def test_list_uncategorized_groups_aggregates_by_description(tmp_path):
    conn, _ = make_conn_with_fixture_txns(tmp_path)
    groups = {g["description"]: g for g in list_uncategorized_groups(conn)}
    assert groups["FAKE SHOP LTD"]["n"] == 2
    assert groups["FAKE SHOP LTD"]["total"] == -25.0
    assert groups["FAKE SHOP LTD"]["min_date"] == "2026-08-01"
    assert groups["FAKE SHOP LTD"]["max_date"] == "2026-08-05"


def test_list_uncategorized_groups_includes_account_name(tmp_path):
    conn, _ = make_conn_with_fixture_txns(tmp_path)
    groups = {g["description"]: g for g in list_uncategorized_groups(conn)}
    assert groups["FAKE SHOP LTD"]["accounts"] == "Main"


def test_list_uncategorized_groups_lists_all_accounts_a_description_spans(tmp_path):
    conn, _ = make_conn_with_fixture_txns(tmp_path)
    other_account_id = get_or_create_account(conn, "OtherBank", "credit_card", "Other Card")
    # Same payee text showing up on a second account too.
    upsert_transaction(conn, other_account_id, "2026-08-10", -20.0, "FAKE SHOP LTD", None, "Uncategorized", "test", "e5")
    conn.commit()

    groups = {g["description"]: g for g in list_uncategorized_groups(conn)}
    accounts = set(groups["FAKE SHOP LTD"]["accounts"].split(","))
    assert accounts == {"Main", "Other Card"}
    assert groups["FAKE SHOP LTD"]["n"] == 3


def test_list_uncategorized_groups_ordered_by_absolute_total_desc(tmp_path):
    conn, _ = make_conn_with_fixture_txns(tmp_path)
    groups = list_uncategorized_groups(conn)
    # FAKE SALARY LTD (100.0) has a bigger absolute total than FAKE SHOP
    # LTD (25.0 across two rows), so it should be triaged first.
    assert groups[0]["description"] == "FAKE SALARY LTD"


def test_set_category_for_description_only_updates_uncategorized(tmp_path):
    conn, _ = make_conn_with_fixture_txns(tmp_path)
    updated = set_category_for_description(conn, "FAKE SHOP LTD", "Shopping")
    assert updated == 2

    rows = conn.execute("SELECT category FROM transactions WHERE description = 'FAKE SHOP LTD'").fetchall()
    assert all(r["category"] == "Shopping" for r in rows)

    # The already-categorized "ALREADY DONE" row is untouched even though
    # it's a different description -- sanity check scoping is right.
    row = conn.execute("SELECT category FROM transactions WHERE description = 'ALREADY DONE'").fetchone()
    assert row["category"] == "Groceries"


def test_set_category_for_description_returns_zero_when_nothing_matches(tmp_path):
    conn, _ = make_conn_with_fixture_txns(tmp_path)
    assert set_category_for_description(conn, "NO SUCH DESCRIPTION", "Shopping") == 0


def test_add_category_updates_db_and_yaml(tmp_path):
    categories_path = tmp_path / "categories.yaml"
    categories_path.write_text("categories:\n  - name: Income\n    parent: null\n")
    conn, _ = make_conn_with_fixture_txns(tmp_path, categories_config=categories_path)

    add_category(categories_path, conn, "Fun Money")

    db_names = {r["name"] for r in conn.execute("SELECT name FROM categories")}
    assert "Fun Money" in db_names

    import yaml

    yaml_names = {c["name"] for c in yaml.safe_load(categories_path.read_text())["categories"]}
    assert "Fun Money" in yaml_names
    # Original entry is still there -- append shouldn't clobber it.
    assert "Income" in yaml_names


def test_add_category_is_idempotent(tmp_path):
    categories_path = tmp_path / "categories.yaml"
    categories_path.write_text("categories:\n  - name: Income\n    parent: null\n")
    conn, _ = make_conn_with_fixture_txns(tmp_path, categories_config=categories_path)

    add_category(categories_path, conn, "Fun Money")
    add_category(categories_path, conn, "Fun Money")

    import yaml

    names = [c["name"] for c in yaml.safe_load(categories_path.read_text())["categories"]]
    assert names.count("Fun Money") == 1


def test_add_rule_appends_without_clobbering_existing_content(tmp_path):
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text('# a helpful comment\nrules:\n  - pattern: "tesco"\n    category: Groceries\n')

    add_rule(rules_path, "fake shop ltd", "Shopping")

    text = rules_path.read_text()
    assert "# a helpful comment" in text
    assert 'pattern: "tesco"' in text or "pattern: tesco" in text

    import yaml

    data = yaml.safe_load(text)
    patterns = {r["pattern"]: r["category"] for r in data["rules"]}
    assert patterns["fake shop ltd"] == "Shopping"
    assert patterns["tesco"] == "Groceries"


def test_add_rule_with_a_label(tmp_path):
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text("rules: []\n")

    add_rule(rules_path, "MERCHANT123", "Household Contribution", label="Some cryptic merchant code")

    import yaml

    data = yaml.safe_load(rules_path.read_text())
    assert data["rules"][0]["label"] == "Some cryptic merchant code"


def test_add_rule_without_a_label_omits_the_key(tmp_path):
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text("rules: []\n")

    add_rule(rules_path, "tesco", "Groceries")

    text = rules_path.read_text()
    assert "label" not in text


def test_add_rule_to_an_empty_flow_style_list_produces_valid_yaml(tmp_path):
    """rules: [] (empty, flow-style) can't just have a block-style item
    appended below it as-is -- that's invalid YAML (mixing list styles for
    the same key). Regression test for exactly that.
    """
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text("rules: []\n")

    add_rule(rules_path, "tesco", "Groceries")

    import yaml

    data = yaml.safe_load(rules_path.read_text())  # raises if invalid
    assert data["rules"] == [{"pattern": "tesco", "category": "Groceries"}]


def test_add_category_to_an_empty_flow_style_list_produces_valid_yaml(tmp_path):
    categories_path = tmp_path / "categories.yaml"
    categories_path.write_text("categories: []\n")
    conn, _ = make_conn_with_fixture_txns(tmp_path, categories_config=categories_path)

    add_category(categories_path, conn, "Fun Money")

    import yaml

    data = yaml.safe_load(categories_path.read_text())  # raises if invalid
    assert data["categories"] == [{"name": "Fun Money", "parent": None}]
