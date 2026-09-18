# Architecture

C4-model diagrams for `money`, grounded in the current codebase and
`tickets/` (see `findings.md` and `adr.md` for the evidence and decisions
behind these). All diagrams are Mermaid `flowchart`/`sequenceDiagram`/
`stateDiagram-v2` blocks (not native Mermaid C4 types — see
`.claude/skills/architecture/SKILL.md` for why), rendered and visually
checked (no overlapping labels, no arrows through box interiors) before
this file was considered finished.

## Context

One person, running a local CLI on their own machine. The only outbound
network call this system makes itself is to Monzo's API; every other bank
is integrated by the user manually downloading a PDF statement and
feeding it in.

```mermaid
flowchart TB
    classDef person fill:#08427b,color:#fff,stroke:#052e56,stroke-width:1px
    classDef extsys fill:#8a8a8a,color:#fff,stroke:#6b6b6b,stroke-width:1px
    classDef system fill:#1168bd,color:#fff,stroke:#0b4884,stroke-width:1px

    User(["<b>You</b><br/>[Person]<br/>Runs commands, reviews reports, downloads PDF statements"])
    Money["<b>money</b><br/>[System]<br/>Local CLI: imports transactions, categorizes spend, tracks budget/debt/discretionary income"]
    Monzo["<b>Monzo API</b><br/>[External System]<br/>OAuth + REST, provides transaction and balance data"]
    Banks["<b>Bank websites/apps</b><br/>[External System]<br/>NatWest, Santander, Capital One - PDF statement download only, no API integration"]

    User -->|Runs commands, e.g. money import-pdf, money report| Money
    Money -->|OAuth login, fetch transactions and balance| Monzo
    User -->|Downloads a PDF statement from| Banks
    User -->|Feeds the downloaded PDF to| Money

    class User person
    class Money system
    class Monzo,Banks extsys
```

## Container

Inside the `money` process: an argparse CLI dispatching to two importers
(source-specific), a shared categorization engine (source-agnostic), and
an analysis/reporting layer, all reading and writing one local SQLite
file and a set of local YAML/`.env` config files.

```mermaid
flowchart TB
    classDef person fill:#08427b,color:#fff,stroke:#052e56,stroke-width:1px
    classDef extsys fill:#8a8a8a,color:#fff,stroke:#6b6b6b,stroke-width:1px
    classDef container fill:#438dd5,color:#fff,stroke:#2e6295,stroke-width:1px
    classDef containerdb fill:#438dd5,color:#fff,stroke:#2e6295,stroke-width:1px

    User(["<b>You</b><br/>[Person]"])
    Monzo["<b>Monzo API</b><br/>[External System]"]

    subgraph SYS["money (local Python process)"]
        CLI["<b>CLI</b><br/>[Container: Python/argparse]<br/>src/money/cli.py - command dispatch, config existence checks"]
        MonzoImp["<b>Monzo Importer</b><br/>[Container: Python]<br/>src/money/importers/monzo.py - OAuth, token refresh, transaction/balance fetch"]
        PdfImp["<b>PDF Importer</b><br/>[Container: Python + pdfplumber]<br/>src/money/importers/pdf_import.py - 4-strategy statement parser"]
        Cat["<b>Categorization Engine</b><br/>[Container: Python]<br/>src/money/categorize.py + review.py - rule matching, interactive review"]
        Analysis["<b>Analysis and Reporting</b><br/>[Container: Python]<br/>budget.py, debt.py, discretionary.py, reports.py"]
        Config["<b>Local Config Store</b><br/>[Container: YAML + .env]<br/>config/*.yaml, .env - categories, rules, budget, debt, secrets"]
        DB[("<b>SQLite DB</b><br/>[Container: SQLite]<br/>data/money.db - accounts, transactions, balances, categories")]
    end

    User -->|Runs commands| CLI
    CLI --> MonzoImp
    CLI --> PdfImp
    CLI --> Cat
    CLI --> Analysis
    CLI -->|init/seed| DB

    MonzoImp -->|OAuth + REST| Monzo
    MonzoImp -->|categorize each row at import| Cat
    PdfImp -->|categorize each row at import| Cat
    Cat -->|read rules, env rules| Config
    Cat -->|upsert categorized transactions| DB

    Analysis -->|budget + debt yaml, read/write| Config
    Analysis -->|read transactions, balances, categories| DB

    class User person
    class Monzo extsys
    class CLI,MonzoImp,PdfImp,Cat,Analysis container
    class DB,Config containerdb
```

## Component: PDF Importer

The most structurally complex container — one dispatcher over four
genuinely different parsing strategies, since four real bank exports
needed four different approaches (see `tickets/0003-pdf-statement-import.md`,
`architecture/findings.md`).

```mermaid
flowchart TB
    classDef component fill:#85bbf0,color:#000,stroke:#5d82a8,stroke-width:1px
    classDef containerdb fill:#438dd5,color:#fff,stroke:#2e6295,stroke-width:1px

    FmtLoader["<b>Format Loader</b><br/>[Component: load_pdf_format]<br/>Reads config/pdf_formats/&lt;bank&gt;.yaml"]
    Dispatcher["<b>Layout Dispatcher</b><br/>[Component: parse_transactions]<br/>Picks a strategy from which keys the format file sets"]
    LineParser["<b>line_types Parser</b><br/>[Component: parse_transactions_from_lines]<br/>NatWest current account - Type-vocabulary anchored regex"]
    DatePairParser["<b>date_pair Parser</b><br/>[Component: parse_transactions_from_date_pair_lines]<br/>NatWest credit card - two-leading-dates anchored"]
    PositionedParser["<b>positioned_columns Parser</b><br/>[Component: parse_transactions_from_positioned_lines]<br/>Capital One - word x-coordinates disambiguate Paid in/out"]
    TableParser["<b>table_columns Parser</b><br/>[Component: parse_transactions_from_table]<br/>Santander - real drawn table via pdfplumber"]
    BalanceExtractor["<b>Balance Extractor</b><br/>[Component: extract_closing_balance]<br/>Regex match on a per-bank balance_label_pattern"]
    Importer["<b>Import/Upsert</b><br/>[Component: import_pdf]<br/>Categorizes each row, upserts transactions + balance"]
    DB[("SQLite DB")]

    FmtLoader --> Dispatcher
    Dispatcher --> LineParser
    Dispatcher --> DatePairParser
    Dispatcher --> PositionedParser
    Dispatcher --> TableParser
    LineParser --> Importer
    DatePairParser --> Importer
    PositionedParser --> Importer
    TableParser --> Importer
    FmtLoader --> BalanceExtractor
    BalanceExtractor --> Importer
    Importer --> DB

    class FmtLoader,Dispatcher,LineParser,DatePairParser,PositionedParser,TableParser,BalanceExtractor,Importer component
    class DB containerdb
```

## Component: Analysis and Reporting

Four independent read paths over the same DB and category tree, one
config file each for the two that carry saved targets (budget, debt).

```mermaid
flowchart TB
    classDef component fill:#85bbf0,color:#000,stroke:#5d82a8,stroke-width:1px
    classDef containerdb fill:#438dd5,color:#fff,stroke:#2e6295,stroke-width:1px

    Budget["<b>Budget</b><br/>[Component: budget.py]<br/>suggest_budget, load/save_budget"]
    DebtPlan["<b>Debt Planner</b><br/>[Component: debt.py]<br/>effective_apr, simulate_avalanche"]
    Discretionary["<b>Discretionary Income</b><br/>[Component: discretionary.py]<br/>resolve_bucket, compute_discretionary"]
    CoreReports["<b>Core Reports</b><br/>[Component: reports.py]<br/>net_worth, spending, household, budget_vs_actual"]
    DB[("SQLite DB<br/>transactions, balances, categories")]
    BudgetYaml[("config/budget.yaml")]
    DebtYaml[("config/debt.yaml")]

    Budget -->|read| DB
    Budget -->|read/write| BudgetYaml
    DebtPlan -->|read/write| DebtYaml
    Discretionary -->|read| DB
    Discretionary -->|debt minimum/extra, matches debt plan --extra| DebtPlan
    CoreReports -->|read| DB
    CoreReports -->|compare actual vs saved| BudgetYaml

    class Budget,DebtPlan,Discretionary,CoreReports component
    class DB,BudgetYaml,DebtYaml containerdb
```

## Sequence: `money import-pdf`

The cross-container flow for a single PDF import, from CLI invocation to
both tables being written.

```mermaid
sequenceDiagram
    actor User
    participant CLI
    participant PdfImporter as PDF Importer
    participant CatEngine as Categorization Engine
    participant DB as SQLite DB

    User->>CLI: money import-pdf --bank natwest --account-name ...
    CLI->>PdfImporter: load_pdf_format(bank)
    PdfImporter-->>CLI: format config (parsing strategy, patterns)
    CLI->>PdfImporter: import_pdf(pdf_path, bank, account, rules)
    PdfImporter->>PdfImporter: parse_transactions(pdf_path, fmt)
    loop each parsed row
        PdfImporter->>CatEngine: categorize(description, merchant, rules)
        CatEngine-->>PdfImporter: category (or Uncategorized)
        PdfImporter->>DB: upsert_transaction(row, category, external_id)
    end
    PdfImporter->>PdfImporter: extract_closing_balance(pdf_path, fmt)
    alt balance_label_pattern matched
        PdfImporter->>DB: record_balance(account, snapshot_date, balance)
    end
    PdfImporter-->>CLI: summary (inserted, updated, balance_recorded)
    CLI-->>User: print summary
```

## State: transaction categorization lifecycle

The only entity in this system with a real lifecycle worth diagramming —
a transaction moves between two categorization states, and can be
re-categorized on a later re-import if rules changed in between.

```mermaid
stateDiagram-v2
    [*] --> Uncategorized: imported, no rule matched
    [*] --> Categorized: imported, a rule matched
    Uncategorized --> Categorized: money categorize (manual assignment) or a new rule added, then re-import
    Categorized --> Categorized: re-import same external_id after a rule change (category refreshed via upsert)
```
