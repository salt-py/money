"""Command-line entrypoint: python -m money.cli <command> ...

Run this yourself, in your own terminal -- commands that touch real bank
credentials or real financial data are not meant to be run by an AI
assistant on your behalf. See README.md for full setup.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from money.categorize import load_env_rules, load_rules
from money.db import get_connection, init_db

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
CONFIG_DIR = BASE_DIR / "config"
REPORTS_DIR = BASE_DIR / "reports"

DB_PATH = DATA_DIR / "money.db"
CATEGORIES_CONFIG = CONFIG_DIR / "categories.yaml"
RULES_CONFIG = CONFIG_DIR / "rules.yaml"
BUDGET_CONFIG = CONFIG_DIR / "budget.yaml"
DEBT_CONFIG = CONFIG_DIR / "debt.yaml"
PDF_FORMATS_DIR = CONFIG_DIR / "pdf_formats"
MONZO_TOKEN_PATH = DATA_DIR / "monzo_tokens.json"


def _require_config(path: Path) -> None:
    # categories.yaml/rules.yaml are personal (gitignored, per-user) --
    # a fresh clone won't have them yet. Point at the tracked .example
    # starter instead of a bare FileNotFoundError traceback.
    if not path.exists():
        example = path.with_suffix(path.suffix + ".example")
        sys.exit(f"{path} not found. Copy {example.name} to {path.name} and edit it to fit your own categories.")


def _load_all_rules():
    _require_config(RULES_CONFIG)
    # Env-based rules first so a specific, real-account-number match (set
    # in .env, gitignored) always wins over the generic yaml rules.
    return load_env_rules() + load_rules(RULES_CONFIG)


def _open_db():
    _require_config(CATEGORIES_CONFIG)
    conn = get_connection(DB_PATH)
    init_db(conn, CATEGORIES_CONFIG)
    return conn


def cmd_init_db(args):
    _open_db()
    print(f"Database ready at {DB_PATH}")


def cmd_monzo_auth(args):
    from money.importers.monzo import authorize, save_token_store, DEFAULT_REDIRECT_URI

    client_id = os.environ["MONZO_CLIENT_ID"]
    client_secret = os.environ["MONZO_CLIENT_SECRET"]
    redirect_uri = os.environ.get("MONZO_REDIRECT_URI", DEFAULT_REDIRECT_URI)
    tokens = authorize(client_id, client_secret, redirect_uri)
    save_token_store(MONZO_TOKEN_PATH, tokens)
    print(f"Monzo tokens saved to {MONZO_TOKEN_PATH}")


def cmd_import_monzo(args):
    from money.importers.monzo import parse_account_name_overrides, run_import

    conn = _open_db()
    rules = _load_all_rules()
    client_id = os.environ["MONZO_CLIENT_ID"]
    client_secret = os.environ["MONZO_CLIENT_SECRET"]
    overrides = parse_account_name_overrides(os.environ.get("MONZO_ACCOUNT_NAME_OVERRIDES", ""))
    summary = run_import(conn, client_id, client_secret, MONZO_TOKEN_PATH, rules, account_name_overrides=overrides)
    for acc in summary["accounts"]:
        print(f"{acc['name']}: {acc['inserted']} new, {acc['updated']} updated")


def cmd_import_pdf(args):
    from money.importers.pdf_import import dry_run_summary, import_pdf, load_pdf_format

    pdf_path = Path(args.path)

    if args.dry_run:
        fmt = load_pdf_format(args.bank, PDF_FORMATS_DIR)
        summary = dry_run_summary(pdf_path, fmt)
        print(f"Pages: {summary['pages']}, text lines: {summary['text_line_count']}")
        print(f"Detected statement date range: {summary['statement_range']}")
        print(f"Transactions parsed: {summary['transactions_parsed']}")
        print(
            "\n(This summary is counts and the statement's overall date "
            "range only -- no real transaction content -- safe to paste "
            "back for help.)"
        )
        if summary["transactions_parsed"] == 0:
            print(
                "\nNo transactions parsed. If statement_range is null, the "
                f"'From .../ To ...' dates weren't found on page 1 of the PDF. "
                f"Otherwise, line_types in config/pdf_formats/{args.bank}.yaml "
                "likely doesn't match this statement's actual 'Type' column "
                "values -- open the PDF yourself and check (that's real data, "
                "so read it locally rather than pasting it here)."
            )
        return

    conn = _open_db()
    rules = _load_all_rules()
    result = import_pdf(
        conn,
        pdf_path=pdf_path,
        bank=args.bank,
        account_name=args.account_name,
        account_type=args.account_type,
        rules=rules,
        formats_dir=PDF_FORMATS_DIR,
    )
    print(f"{result['inserted']} new, {result['updated']} updated")


def cmd_categories(args):
    """Prints the category taxonomy as real YAML, with each category's
    config/rules.yaml patterns nested underneath it as a `rules:` list --
    structure only, no financial figures or real transaction content, so
    unlike almost everything else in this CLI it's safe to run and share
    regardless of the "run this yourself" rule. Env-based rules
    (money/categorize.py's ENV_RULE_CATEGORIES) are shown by their .env
    variable *name* only -- never the real value (e.g. an account number)
    that variable holds.

    Each rule is shown as its `label` when set, falling back to the raw
    regex pattern only when there's no label -- not both, so the output
    stays readable rather than doubling every entry.

    An optional `category` argument prints just that category's subtree
    (a "portion" of the full tree) instead of everything.
    """
    from money.categorize import ENV_RULE_CATEGORIES, load_rules

    conn = _open_db()
    rows = conn.execute("SELECT name, parent FROM categories").fetchall()
    children: dict[str | None, list[str]] = {}
    all_names: set[str] = set()
    for row in rows:
        children.setdefault(row["parent"], []).append(row["name"])
        all_names.add(row["name"])
    for names in children.values():
        names.sort()

    rules_by_category: dict[str, list[tuple[str, str | None]]] = {}
    for rule in load_rules(RULES_CONFIG):
        rules_by_category.setdefault(rule.category, []).append((rule.pattern.pattern, rule.label))

    env_vars_by_category: dict[str, list[str]] = {}
    for env_var, category in ENV_RULE_CATEGORIES.items():
        env_vars_by_category.setdefault(category, []).append(env_var)

    def build_node(name: str, seen: frozenset[str] = frozenset()) -> dict:
        node: dict = {}
        rule_lines = [label if label else pattern for pattern, label in rules_by_category.get(name, [])]
        rule_lines += [f"(from .env {env_var}, value not shown)" for env_var in env_vars_by_category.get(name, [])]
        if rule_lines:
            node["rules"] = rule_lines
        if name in seen or len(seen) > 10:
            return node  # guard against an accidental cycle in categories.yaml
        for child in children.get(name, []):
            node[child] = build_node(child, seen | {name})
        return node

    requested = getattr(args, "category", None)
    if requested is not None:
        if requested not in all_names:
            print(f"No such category: {requested}")
            return
        tree = {requested: build_node(requested)}
    else:
        tree = {root: build_node(root) for root in sorted(children.get(None, []))}

    print(yaml.safe_dump(tree, default_flow_style=False, sort_keys=False, allow_unicode=True), end="")


def cmd_categorize(args):
    from money.review import add_category, add_rule, list_uncategorized_groups, set_category_for_description

    conn = _open_db()
    categories = [row["name"] for row in conn.execute("SELECT name FROM categories ORDER BY name")]
    groups = list_uncategorized_groups(conn)
    if not groups:
        print("No uncategorized transactions.")
        return

    total_txns = sum(g["n"] for g in groups)
    print(f"{len(groups)} distinct uncategorized description(s), {total_txns} transaction(s) total.")
    print("For each: pick a category by number, 'n' for a new category, 's' to skip, 'q' to quit.\n")

    done = 0
    for i, g in enumerate(groups, 1):
        print(f"[{i}/{len(groups)}] {g['description']!r}  x{g['n']}  total {g['total']:.2f}  "
              f"({g['min_date']} to {g['max_date']})  [{g['accounts'].replace(',', ', ')}]")
        for idx, cat in enumerate(categories, 1):
            print(f"  {idx}) {cat}")
        print("  n) new category   s) skip   q) quit")
        choice = input("> ").strip().lower()

        if choice in ("q", ""):
            break
        if choice == "s":
            print()
            continue

        if choice == "n":
            category = input("New category name: ").strip()
            if not category:
                print("  (empty, skipping)\n")
                continue
            if category not in categories:
                bucket = input(
                    "  Discretionary, Non-Discretionary, or neither (blank -- e.g. a "
                    "transfer/reimbursement that isn't really spend)? [d/n/blank]: "
                ).strip().lower()
                parent = {"d": "Discretionary", "n": "Non-Discretionary"}.get(bucket)
                add_category(CATEGORIES_CONFIG, conn, category, parent=parent)
                categories.append(category)
        elif choice.isdigit() and 1 <= int(choice) <= len(categories):
            category = categories[int(choice) - 1]
        else:
            print("  (not understood, skipping)\n")
            continue

        updated = set_category_for_description(conn, g["description"], category)
        done += 1
        print(f"  -> {updated} transaction(s) set to '{category}'")

        save = input("  Save a rule so future imports auto-categorize this too? [y/N]: ").strip().lower()
        if save == "y":
            default_pattern = re.escape(g["description"])
            pattern = input(f"  Pattern (regex, case-insensitive) [{default_pattern}]: ").strip() or default_pattern
            label = input("  Friendly name for this rule (optional, shown in `money categories`): ").strip()
            add_rule(RULES_CONFIG, pattern, category, label=label or None)
            suffix = f" ({label})" if label else ""
            print(f"  -> rule added to {RULES_CONFIG.name}: \"{pattern}\"{suffix} -> {category}")
        print()

    print(f"Categorized {done} of {len(groups)} description(s) this session.")


def cmd_budget(args):
    from money.budget import load_budget, save_budget, suggest_budget

    conn = _open_db()

    if args.budget_action == "suggest":
        result = suggest_budget(conn, months=args.months)
        print(
            f"Suggested monthly budget based on the last {result['months']} month(s) "
            f"(since {result['start_date']}):\n"
        )
        if not result["categories"]:
            print("  No spending found in that window.")
        for c in result["categories"]:
            print(
                f"  {c['category']:25s} {c['monthly_average']:>10.2f}  "
                f"(total {c['total']:.2f} across {c['transaction_count']} txn(s))"
            )
        if args.save:
            budget = {c["category"]: c["monthly_average"] for c in result["categories"]}
            save_budget(BUDGET_CONFIG, budget)
            print(f"\nSaved to {BUDGET_CONFIG}")
        else:
            print(
                f"\nThis is a starting point, not a prescription -- edit the numbers to "
                f"taste. Run with --save to write it to {BUDGET_CONFIG.name}, or edit that "
                f"file by hand once it exists."
            )

    elif args.budget_action == "show":
        budget = load_budget(BUDGET_CONFIG)
        if not budget:
            print(f"No budget saved yet at {BUDGET_CONFIG}. Run `money budget suggest --save` first.")
            return
        print("Current budget:")
        for category, amount in sorted(budget.items()):
            print(f"  {category:25s} {amount:>10.2f}")


def _prompt_promo_fields(prior: dict) -> dict:
    """Asks whether a debt is on a promotional/intro rate right now (e.g. a
    0% balance transfer). Returns {} for no promo, or
    {"promo_apr": ..., "promo_until": ...} -- the rate reverts to the
    debt's normal APR on that date.
    """
    has_prior_promo = prior.get("promo_until") is not None
    suffix = " [keep existing promo]" if has_prior_promo else ""
    resp = input(f"  On a promotional/intro rate right now?{suffix} [y/N]: ").strip().lower()
    if resp == "y":
        promo_apr_raw = input("  Promotional APR (%) [0]: ").strip()
        promo_apr = float(promo_apr_raw) if promo_apr_raw else 0.0
        promo_until = input("  Promo reverts to the normal APR on (YYYY-MM-DD): ").strip()
        if promo_until:
            return {"promo_apr": promo_apr, "promo_until": promo_until}
        print("  (no end date given, not saving a promo rate)")
        return {}
    if resp == "n":
        return {}
    return {"promo_apr": prior["promo_apr"], "promo_until": prior["promo_until"]} if has_prior_promo else {}


def cmd_debt(args):
    from money.debt import get_tracked_debt_accounts, load_debts, save_debts, simulate_avalanche

    conn = _open_db()

    if args.debt_action == "setup":
        existing = load_debts(DEBT_CONFIG)
        tracked = get_tracked_debt_accounts(conn)
        debts = dict(existing)

        print("Auto-detected accounts with a tracked negative balance:")
        if not tracked:
            print(
                "  (none found -- a credit card needs a balance_label_pattern in its "
                "config/pdf_formats/<bank>.yaml and at least one import; Monzo needs to "
                "actually be overdrawn. An overdraft on an account without balance "
                "tracking, e.g. NatWest current, won't show up here -- add it manually below.)"
            )
        for acc in tracked:
            name = acc["name"]
            prior = existing.get(name, {})
            print(f"\n{name}  (tracked balance: {acc['balance']:.2f})")
            apr_suffix = f" [{prior['apr']}]" if "apr" in prior else ", blank to skip this debt"
            apr_raw = input(f"  APR (%) -- the normal rate, after any promo ends{apr_suffix}: ").strip()
            if not apr_raw and "apr" not in prior:
                print("  (skipped)")
                continue
            apr = float(apr_raw) if apr_raw else prior["apr"]
            min_suffix = f" [{prior.get('min_payment', 0)}]" if "min_payment" in prior else ""
            min_raw = input(f"  Minimum payment{min_suffix}: ").strip()
            min_payment = float(min_raw) if min_raw else prior.get("min_payment", 0.0)
            debts[name] = {"balance": acc["balance"], "apr": apr, "min_payment": min_payment}
            debts[name].update(_prompt_promo_fields(prior))

        print("\nAdd any other debts not tracked automatically (e.g. an overdraft)?")
        while input("Add one? [y/N]: ").strip().lower() == "y":
            name = input("  Name: ").strip()
            if not name:
                print("  (empty name, skipping)")
                continue
            try:
                balance = float(input("  Balance (positive = amount owed): ").strip())
                apr = float(input("  APR (%) -- the normal rate, after any promo ends: ").strip())
            except ValueError:
                print("  (balance and APR must be numbers, skipping this debt)")
                continue
            min_raw = input("  Minimum payment [0]: ").strip()
            min_payment = float(min_raw) if min_raw else 0.0
            debts[name] = {"balance": balance, "apr": apr, "min_payment": min_payment}
            debts[name].update(_prompt_promo_fields({}))

        if debts:
            save_debts(DEBT_CONFIG, debts)
            print(f"\nSaved {len(debts)} debt(s) to {DEBT_CONFIG}")
        else:
            print("\nNo debts entered, nothing saved.")

    elif args.debt_action == "show":
        debts = load_debts(DEBT_CONFIG)
        if not debts:
            print(f"No debts saved yet at {DEBT_CONFIG}. Run `money debt setup` first.")
            return
        print("Current debts:")
        total = 0.0
        for name, d in sorted(debts.items()):
            promo = (
                f"  (promo {d['promo_apr']:.2f}% until {d['promo_until']})"
                if d.get("promo_until") else ""
            )
            print(
                f"  {name:25s} balance {d['balance']:>10.2f}  APR {d['apr']:>6.2f}%  "
                f"min payment {d['min_payment']:>8.2f}{promo}"
            )
            total += d["balance"]
        print(f"  {'TOTAL':25s} balance {total:>10.2f}")

    elif args.debt_action == "plan":
        debts = load_debts(DEBT_CONFIG)
        if not debts:
            print(f"No debts saved yet at {DEBT_CONFIG}. Run `money debt setup` first.")
            return
        result = simulate_avalanche(debts, extra_monthly=args.extra)
        if result["months"] is None:
            print(
                f"With {args.extra:.2f}/month extra on top of minimums, this doesn't pay "
                f"off within 50 years -- the budget doesn't even cover the interest "
                f"accruing. You need a bigger monthly amount, a lower rate (balance "
                f"transfer?), or both."
            )
            return

        print(
            f"Debt payoff plan (avalanche: highest APR first), "
            f"{args.extra:.2f}/month extra beyond minimums:\n"
        )
        for i, d in enumerate(result["payoff_order"], 1):
            promo = f"  (promo {d['promo_apr']:.2f}% until {d['promo_until']})" if d.get("promo_until") else ""
            print(
                f"  {i}. {d['name']:25s} balance {d['balance']:>10.2f}  APR {d['apr']:>6.2f}%  "
                f"min {d['min_payment']:>8.2f}  paid off month {d['payoff_month']} ({d['payoff_date']}){promo}"
            )
        years, months_rem = divmod(result["months"], 12)
        print(
            f"\nDebt-free in {result['months']} months ({years}y {months_rem}m), "
            f"total interest paid: {result['total_interest']:.2f}"
        )


def cmd_report(args):
    from money import reports
    from money.budget import load_budget
    from money.debt import load_debts

    conn = _open_db()
    if args.report == "net-worth":
        reports.net_worth(conn, since=args.since)
    elif args.report == "spending":
        reports.spending(conn, month=args.month, by=args.by)
    elif args.report == "household":
        reports.household(conn, month=args.month)
    elif args.report == "budget":
        reports.budget_vs_actual(conn, month=args.month, budget=load_budget(BUDGET_CONFIG))
    elif args.report == "discretionary":
        debts = load_debts(DEBT_CONFIG)
        debt_minimum_total = sum(d["min_payment"] for d in debts.values())
        reports.discretionary(
            conn, month=args.month, debt_minimum_total=debt_minimum_total, debt_extra=args.debt_extra
        )


EPILOG = """\
typical flow:
  money init-db
  money monzo-auth                                        (one-time)
  money import-monzo
  money import-pdf statement.pdf --bank natwest --account-name "NatWest Current Account"
  money categorize
  money report spending --month 2026-08
  money budget suggest --save
  money report budget --month 2026-08
  money debt setup
  money debt plan --extra 200

run `money <command> -h` (or `money report <report> -h`, `money budget <action> -h`)
for details on any command. See README.md for full setup instructions.

every command here is meant to be run by you, in your own terminal -- not
pasted to, or run on your behalf by, an AI assistant, since most of them
touch real bank credentials or real financial data.
"""


def _add_cmd(sub, name: str, text: str, **kwargs):
    """add_parser wrapper that uses the same one-liner for both the
    parent's command listing (`help=`) and that command's own `--help`
    header (`description=`), so `money <command> -h` isn't blank.
    """
    return sub.add_parser(name, help=text, description=text, **kwargs)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="money",
        description="A local-only personal finance tracker: pulls transactions from "
        "Monzo (API) and other banks (PDF statements) into a local SQLite database, "
        "with categorization, reports, and a rough budget on top.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    _add_cmd(sub, "init-db", "create/verify the local database and seed categories").set_defaults(func=cmd_init_db)

    _add_cmd(sub, "monzo-auth", "one-time interactive OAuth login to Monzo (opens a browser)").set_defaults(
        func=cmd_monzo_auth
    )
    _add_cmd(sub, "import-monzo", "pull new transactions + balance from Monzo via its API").set_defaults(
        func=cmd_import_monzo
    )

    pdf_p = _add_cmd(
        sub, "import-pdf", "import transactions from a bank statement PDF (NatWest, Santander, Capital One, ...)"
    )
    pdf_p.add_argument("path", help="path to the statement PDF, e.g. data/statement.pdf")
    pdf_p.add_argument("--bank", required=True, help="matches a file in config/pdf_formats/, e.g. natwest")
    pdf_p.add_argument("--account-name", required=True, help='label for this account, e.g. "NatWest Current Account"')
    pdf_p.add_argument("--account-type", default="current", help="e.g. current, credit_card, savings (default: current)")
    pdf_p.add_argument(
        "--dry-run", action="store_true",
        help="print page/line/transaction counts and detected date range only, import nothing",
    )
    pdf_p.set_defaults(func=cmd_import_pdf)

    _add_cmd(
        sub, "categorize", "interactively review and assign categories to Uncategorized transactions"
    ).set_defaults(func=cmd_categorize)

    categories_p = _add_cmd(
        sub, "categories", "print the category taxonomy as YAML (names/structure only, no financial data)"
    )
    categories_p.add_argument(
        "category", nargs="?", default=None,
        help="only print this category and its descendants, instead of the whole tree",
    )
    categories_p.set_defaults(func=cmd_categories)

    budget_p = _add_cmd(sub, "budget", "suggest or view a monthly budget based on historic spend")
    budget_sub = budget_p.add_subparsers(dest="budget_action", required=True)

    suggest_p = _add_cmd(budget_sub, "suggest", "suggest a budget from trailing average spend per category")
    suggest_p.add_argument("--months", type=int, default=3, help="trailing calendar months to average over (default: 3)")
    suggest_p.add_argument("--save", action="store_true", help=f"write the suggestion to config/{BUDGET_CONFIG.name}")
    suggest_p.set_defaults(func=cmd_budget)

    show_p = _add_cmd(budget_sub, "show", "print the currently saved budget")
    show_p.set_defaults(func=cmd_budget)

    debt_p = _add_cmd(sub, "debt", "track debts (credit cards, overdrafts) and plan a payoff")
    debt_sub = debt_p.add_subparsers(dest="debt_action", required=True)

    debt_setup_p = _add_cmd(
        debt_sub, "setup", "interactively enter balance/APR/minimum payment per debt"
    )
    debt_setup_p.set_defaults(func=cmd_debt)

    debt_show_p = _add_cmd(debt_sub, "show", "print the currently saved debts")
    debt_show_p.set_defaults(func=cmd_debt)

    debt_plan_p = _add_cmd(
        debt_sub, "plan", "simulate an avalanche payoff (highest APR first) and print a timeline"
    )
    debt_plan_p.add_argument(
        "--extra", type=float, default=0.0,
        help="extra amount per month beyond minimum payments to put toward debt (default: 0)",
    )
    debt_plan_p.set_defaults(func=cmd_debt)

    report_p = _add_cmd(sub, "report", "print a report against your local data")
    report_sub = report_p.add_subparsers(dest="report", required=True)

    nw_p = _add_cmd(report_sub, "net-worth", "latest balance per account, and the total")
    nw_p.add_argument("--since", default=None, help="also show total balance trend since this date (YYYY-MM-DD)")
    nw_p.set_defaults(func=cmd_report)

    sp_p = _add_cmd(report_sub, "spending", "spending broken down by category for one month")
    sp_p.add_argument("--month", required=True, help="YYYY-MM")
    sp_p.add_argument("--by", default="category", choices=["category"])
    sp_p.set_defaults(func=cmd_report)

    hh_p = _add_cmd(
        report_sub, "household", "how much went to the household account this month, and what share of income that is"
    )
    hh_p.add_argument("--month", required=True, help="YYYY-MM")
    hh_p.set_defaults(func=cmd_report)

    bg_p = _add_cmd(
        report_sub, "budget", "compare a month's actual spend (money out/in per category) against your saved budget"
    )
    bg_p.add_argument("--month", required=True, help="YYYY-MM")
    bg_p.set_defaults(func=cmd_report)

    disc_p = _add_cmd(
        report_sub, "discretionary",
        "income minus Non-Discretionary spend minus debt commitment = what's actually free to spend",
    )
    disc_p.add_argument("--month", required=True, help="YYYY-MM")
    disc_p.add_argument(
        "--debt-extra", type=float, default=0.0,
        help="also subtract this planned avalanche extra (matches `debt plan --extra`), on top of minimums",
    )
    disc_p.set_defaults(func=cmd_report)

    return parser


def main(argv=None):
    load_dotenv(BASE_DIR / ".env")
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)
    try:
        args.func(args)
    except KeyError as e:
        print(f"Missing required environment variable: {e}. Check your .env file.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
