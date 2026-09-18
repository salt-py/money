# Architecture

C4-model architecture docs for this project, produced by the `architecture`
skill (`.claude/skills/architecture/SKILL.md`).

- **`architecture.md`** — C4 diagrams (Context, Container, Component, plus
  sequence/state diagrams where relevant), as Mermaid `flowchart` blocks.
- **`adr.md`** — Architecture Decision Records, one per real decision.
- **`findings.md`** — the evidence/findings the diagrams and ADRs are
  grounded in.
- **`principles.md`** (once there's an actual principle to put in it) —
  cross-cutting rules that constrain more than one design.

First pass written against the state of the code and `tickets/` as of
2026-09-18. Re-run the skill (or ask to update it) after a structural
change — a new import path, a new report, a change to how categorization
or the DB schema works — rather than letting it drift out of date.
