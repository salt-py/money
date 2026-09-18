# Engineering

**Core need:** Keep the codebase trustworthy, maintainable, and safe to
change — for whoever's maintaining it, present or future.

Unlike the other profiles in this folder, Engineering isn't an end user
of the tool — it's the standing interest of whoever maintains this
codebase (right now, that's one person wearing both hats). Every other
profile's features get built *by* someone reading and changing this code;
Engineering represents the quality bar that makes that sustainable rather
than something that erodes one feature at a time. Its job is to catch the
kind of work that's easy to justify skipping in the moment — tests,
tooling, refactoring a file that's grown too large, closing a gap a real
user profile would never think to ask for — because nobody outside this
file is going to ask for it either.

Use this profile to group technical-quality tickets the same way the
others group user-facing ones: a ticket here should still be traceable to
a concrete risk or cost (a real bug class, a real maintenance pain, a
real gap), not "best practice for its own sake."

## Useful features (of the project, for itself)

- ✅ CI (`.github/workflows/test.yml`) running the full test suite across
  Python 3.10-3.13 on every push/PR.
- ✅ 149 tests, entirely against synthetic fixtures — no test depends on
  real data or a real account, so the suite runs the same for any
  contributor.
- ✅ `architecture/` — a C4 model plus ADRs recording *why* key decisions
  were made, not just what shipped.
- ✅ `tickets/` — retrospective coverage of every shipped feature's key
  decisions and trade-offs.
- ✅ Public-repo hygiene: MIT license, gitignored personal config with
  generic `.example` templates, no real data reachable from git history
  (see `tickets/0010-public-repo-readiness.md`).
- 🔲 Linting/formatting enforced in CI (e.g. `ruff`) — nothing currently
  stops an inconsistent style from landing.
- 🔲 Type checking (e.g. `mypy`) — the codebase already uses type hints
  throughout, but nothing verifies they're honest.
- 🔲 Test coverage reporting — 149 passing tests is a count, not a
  coverage number; no visibility into what's actually exercised.
- 🔲 Dependency update automation (e.g. Dependabot) — pinned/floor
  versions in `pyproject.toml` have no process for staying current.
- 🔲 A `CONTRIBUTING.md` — the repo is public now (`tickets/0010`) but has
  no documented expectations for an external contributor opening a PR.
- 🔲 Splitting up the largest modules — `cli.py` (606 lines) and
  `pdf_import.py` (555 lines) are both doing a lot in one file; worth
  revisiting once either gets harder to navigate, not preemptively.
- 🔲 A basic security/dependency scan (e.g. `pip-audit`) — relevant
  specifically because this tool touches financial data, even though it
  never leaves the user's machine.
