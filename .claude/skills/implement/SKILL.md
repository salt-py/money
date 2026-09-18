---
name: implement
description: "Implement a money ticket end-to-end: scope against architecture/profiles, resolve open questions back into the architecture docs, build, test, publish."
user-invocable: true
argument-hint: "A ticket number/slug (e.g. 0011 or 0011-savings-goals), or a Now/Next row from product/roadmap.md to promote into a new ticket first."
---

# Implement

You are implementing one ticket in `money` end-to-end. The ticket's
**Acceptance criteria** are the definition of done — nothing more,
nothing less. This is a solo personal-finance CLI, not a team codebase:
keep scope tight, don't add process for its own sake, and never touch
real credentials or real data yourself (see `CLAUDE.md` — that rule is
absolute and applies to every step below, not just the obvious ones).

This skill's distinguishing job, beyond "write the code": **implementation
surfaces questions architecture didn't answer. Resolve them, then feed
the resolution back into `architecture/` before moving on** — see step 4.
A ticket that's "done" but left a real design question unrecorded is not
actually done.

## Reference material

Orient yourself before writing code:
- `tickets/<ticket>.md` — the ticket. If it doesn't exist yet, see step 1.
- `tickets/README.md` — the planned-vs-done ticket shape and the
  Acceptance criteria convention this skill drives.
- `architecture/architecture.md`, `adr.md`, `findings.md` — the current
  system model and every real decision behind it. A change that alters
  the Container/Component shape or makes a new architectural decision
  updates these; see step 4.
- `.claude/skills/architecture/SKILL.md` — the diagram conventions and
  validation steps to follow whenever `architecture.md` itself changes.
- `product/<profile>.md` + `product/roadmap.md` — the *why* behind the
  ticket, and the backlog row to update once the ticket ships.
- `tests/` — the existing test suite (synthetic fixtures only; see
  `tests/fixtures/`). Follow the nearest existing test file's pattern
  rather than inventing a new one.

## Workflow

### 1. Scope

- If given a ticket number/slug: read `tickets/<ticket>.md` in full.
- If given a `product/roadmap.md` row instead (no ticket yet): read the
  row, its linked profile(s)' relevant section, and any tickets it
  references, then write a new `tickets/NNNN-short-slug.md` in the
  **planned** shape (`tickets/README.md`) — Status, Summary, Profiles
  (as user stories, copied/adapted from the roadmap row's profile(s)),
  and an **Acceptance criteria** checklist you derive from the roadmap
  row's stated need. Update that row's Status to `Ticketed` and link the
  new ticket in `product/roadmap.md`.
- Read every profile named in the ticket's **Profiles** section in full
  (not just the one line quoted in the ticket) — the ticket's user
  stories are a summary, the profile file has the fuller need and its
  other feature requests, which often disambiguates an otherwise-vague
  acceptance criterion.
- Read `architecture/architecture.md`, `adr.md`, and `findings.md` for
  anything that constrains this ticket: an existing ADR the new work
  must respect, a container/component it will extend rather than
  duplicate, a principle in `architecture/principles.md` if one exists.
- If an acceptance criterion is ambiguous, or conflicts with an existing
  ADR, **ask before continuing** rather than guessing — this is a
  one-person project, so there's no reviewer downstream to catch a wrong
  assumption before it ships.

### 2. Task breakdown

For most tickets in this repo (small, single-repo, usually a day or
less of work) a full separate `tasks/` directory is overkill. Instead:
turn the acceptance criteria into an ordered checklist directly in the
ticket (they're already close to task-shaped) and note any real
dependency between them inline, e.g. `- [ ] Add config/goals.yaml.example
(needed before the CLI command that reads it)`. Only break out separate
task files if the ticket is genuinely large enough that a single
acceptance-criteria list stops being a usable plan — that should be rare
here.

### 3. Branch

- `git checkout -b <slug>` (matching the ticket's filename slug, without
  the number, e.g. `savings-goals`) from `main`.
- Run the full test suite before writing any code, to confirm nothing is
  already broken: `.venv/bin/python -m pytest tests/ -q`.

### 4. Implement

Work through the acceptance criteria in order. For each one:

- **Implement** the change.
- **Test immediately** — run the narrowest relevant test file before
  moving to the next criterion, not just a full suite run at the end.
- **Tick it off** in the ticket (`- [ ]` → `- [x]`) as it's satisfied —
  never batch-tick at the end.

**When a real design question comes up mid-implementation** (config
shape, gitignore-or-not, which module a new component belongs in,
whether an existing convention applies or this case is genuinely
different) — this is the step the CCF version of this skill didn't need
and this repo's does:

1. Resolve it using the same judgment `architecture/adr.md`'s existing
   entries model — state the options, pick one, say why.
2. Write it up immediately as a new `ADR-00N` in `architecture/adr.md`
   (next number in sequence), or as a new dated entry in
   `architecture/findings.md` if it's evidence rather than a decision
   (e.g. "turns out `discretionary.py`'s `resolve_bucket` already handles
   this, no new code needed"). Don't wait until the ticket is finished —
   do it at the moment the question resolves, so the reasoning is still
   fresh and doesn't get flattened into a generic summary later.
3. If the change alters what `architecture.md`'s Container or Component
   diagrams show (a new component, a new data store, a changed
   relationship), update the relevant diagram now, following
   `.claude/skills/architecture/SKILL.md` step 3's style rules, and
   re-validate it (that skill's step 4 — render via `mermaid-cli`,
   actually look at the PNG) before moving on. Don't let the diagrams
   silently drift out of sync with what the code now does.
4. If the resolution reveals a genuine cross-cutting principle (not
   specific to this one ticket), add it to `architecture/principles.md`
   per that skill's step 0.

Common patterns by change type in this codebase:

**New CLI subcommand** (`src/money/cli.py`):
- Follow the existing `_add_cmd()` pattern for both the listing and
  `--help` text; watch for the argparse `%`-substitution landmine noted
  in `tickets/` history (never a literal `%` in help text).
- Add a `cmd_*` function; if it touches personal config, call
  `_require_config()` first, matching every existing command.
- Add tests in `tests/test_cli_<command>.py`, monkeypatching
  `CATEGORIES_CONFIG`/`RULES_CONFIG`/`DB_PATH`/etc. to `tmp_path` fixtures
  — never let a test read the real, gitignored config.

**New personal config file** (e.g. `config/goals.yaml`):
- Gitignore it (same treatment as `config/budget.yaml`/`debt.yaml`) and
  add a generic `config/goals.yaml.example` template — per ADR-006 in
  `architecture/adr.md`, this is now a settled convention, not a
  per-ticket decision.
- Wire a `_require_config()` check into any command that reads it.

**New report or analysis module**:
- Follow `reports.py`'s existing shape (a plain function taking `conn`
  and printing output) unless the new logic is complex enough to
  warrant its own module, the way `budget.py`/`debt.py`/`discretionary.py`
  each did.

### 5. Test

After every acceptance criterion is checked off:

- `.venv/bin/python -m pytest tests/ -q` — full suite, must pass.
- If `architecture.md` changed: re-run the Mermaid extraction/render/
  visual-check from `.claude/skills/architecture/SKILL.md` step 4.
- Confirm no test depends on real, gitignored config — grep the diff for
  any reference to `config/categories.yaml`/`rules.yaml`/`budget.yaml`/
  `debt.yaml` (not their `.example` counterparts) inside `tests/`.
- Sweep the diff for anything that looks like it could be real data
  accidentally used as a "realistic" example (see
  `tickets/0010-public-repo-readiness.md` for exactly this class of bug)
  — new example text in docstrings/comments/README updates should be
  obviously fake, not something recalled from a real statement.

### 6. Rewrite the ticket, roadmap, and profile

- Rewrite `tickets/<ticket>.md` from its planned shape into the done
  shape (`tickets/README.md`): replace **Acceptance criteria** with
  **What shipped**, and add **Key decisions** (pull straight from the
  ADRs/findings written in step 4 rather than re-deriving them). Set
  **Status: Done**.
- Update `product/roadmap.md`: move the row from Now/Next/Later into
  Done (or just update its Status cell to `Done` with a link to the
  ticket — match whatever the file's current shape is at the time).
- Update the relevant `product/<profile>.md` file(s): flip the shipped
  feature from 🔲 to ✅.

### 7. Publish

- `.venv/bin/python -m pytest tests/ -q` once more on the final diff.
- Stage and commit. Follow `CLAUDE.md`: no Claude attribution line.
  Reference the ticket in the commit message (e.g. `"0011: add savings
  goal tracking"`).
- Push the branch and open a PR (`gh pr create`) against `main`,
  summarizing what shipped and linking the ticket. There's no second
  reviewer on this project — the PR is still worth opening (a clean diff
  to read back before merging, and a public record for anyone else
  looking at the repo), but merge it yourself once you're satisfied
  rather than waiting on approval that isn't coming.

## Rules

- Acceptance criteria are the definition of done — don't add scope
  beyond them without going back to step 1 and updating the ticket first.
- Never run a command that touches real credentials or real data
  yourself (`CLAUDE.md`) — if a criterion genuinely requires that (e.g.
  verifying a real PDF import still works), say so explicitly and ask
  the user to run and confirm it themselves, the same way the rest of
  this project already works.
- A resolved design question that isn't written into `architecture/adr.md`
  or `findings.md` didn't happen, as far as the next person (or the next
  session) reading this repo is concerned — see step 4.
- If an assumption is low-risk, state it and keep moving. If it's
  high-risk or contradicts an existing ADR, stop and ask.
- Don't add tests, refactors, or cleanup beyond what the ticket needs —
  same "no unrequested scope" rule as everywhere else in this project.
