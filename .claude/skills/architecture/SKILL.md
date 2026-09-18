---
name: architecture
description: "Produce a C4-model architecture doc set (architecture.md + adr.md + findings.md) in architecture/, following this repo's convention. Use when the user says 'we need an architecture', 'design this following C4', 'write ADRs for this', or asks for architecture/design docs."
---

# Architecture

Produce the three-file bundle this repo uses for architecture work —
`architecture.md` (C4 diagrams), `adr.md` (decisions), `findings.md`
(findings/evidence) — living together in `architecture/` at the repo root.
These three files cross-reference each other; don't produce just one in
isolation unless the user asks for only that piece.

## 0. Before starting

- **Ground everything in this repo's actual code and its `tickets/`
  folder** — don't invent architecture from a description alone. Pull
  concrete detail forward (real module/file names, real CLI commands and
  flags, decisions already recorded in a ticket's own "Key decisions"
  section) into `findings.md` and `adr.md` rather than re-deriving it from
  scratch.
- **Read the existing `architecture/` files first**, once they exist, so
  a later update matches the established tone/structure rather than
  drifting. (The very first time this skill runs in this repo, there's
  nothing to match yet — that first pass sets the precedent.)
- If cross-cutting principles emerge over time (a rule that constrains
  more than one design, not just one decision — e.g. "reports never write
  to `config/*.yaml`, only read it"), record it in
  `architecture/principles.md` and check new designs against it. Start
  that file once there's an actual principle to put in it, not
  preemptively with a placeholder.
- This is a solo project with one small `architecture/` bundle for the
  whole system, not one bundle per ticket — unlike a larger team repo
  where architecture docs might live per-ticket under a `tickets/<project>/<N>/`
  path, everything here lives together at `architecture/` since there's
  one system, not many independently-evolving ones.

## 1. Write `findings.md` first — the evidence

Findings-against-open-questions: what was asked (or what prompted this
pass), what was found, with citations (file:line, a specific ticket in
`tickets/`, a specific commit). Structure around whatever open questions
this piece of work actually had, not a fixed template. If a finding
overturned an earlier, reasonable-looking assumption, say so explicitly —
that's exactly the kind of thing worth recording, not smoothing over.

Reference `tickets/*.md` for full detail on *why* something was built a
given way rather than duplicating it wholesale — `findings.md` is the
synthesis the architecture and ADRs are built on, not a second copy of
every ticket.

## 2. Write `adr.md` — the decisions

One ADR per real decision, numbered `ADR-001`, `ADR-002`, ... Each one:

```markdown
## ADR-00N: <short decision title>

**Status:** Accepted (or "Accepted, provisional pending X" if genuinely not
fully confirmed — phrase an assumed-pending-confirmation decision honestly
rather than overclaiming)

**Context:** What forced this decision — the options, why they existed, and
the concrete evidence available (cite `findings.md` findings).

**Decision:** What was actually decided, stated plainly.

**Consequences:** What this costs or unlocks, including anything it doesn't
resolve or that depends on a follow-up. Flag anything not yet fully
confirmed rather than presenting it as settled.

**Alternatives considered:** What else was on the table and why it was
rejected — not just the winner.
```

Write an explicit ADR for scope boundaries too, not just technical choices
— e.g. why PDF import exists at all instead of an aggregator (see
`tickets/0003-pdf-statement-import.md`) is exactly the kind of thing that
deserves its own ADR, not just a code comment.

## 3. Write `architecture.md` — the diagrams

C4 levels: **Context** (people + external systems + the system as one box),
**Container** (the system's own deployable/runtime pieces), **Component**
(inside the most complex container(s) — split into multiple smaller
diagrams along a natural seam rather than one dense diagram covering
everything). Add sequence diagrams for any cross-system real-time flow and
a state diagram for any entity with a real lifecycle — both are standard
companions to C4, not extra scope.

**Diagram style — this is the part that goes wrong if skipped.** Do NOT use
Mermaid's native `C4Context`/`C4Container`/`C4Component` diagram types —
the native C4 renderer produces overlapping labels and lines cutting
through boxes once a graph has any real density. Use plain `flowchart TB`
styled to carry C4 semantics instead — copy this `classDef` set verbatim:

```
classDef person fill:#08427b,color:#fff,stroke:#052e56,stroke-width:1px
classDef extsys fill:#8a8a8a,color:#fff,stroke:#6b6b6b,stroke-width:1px
classDef system fill:#1168bd,color:#fff,stroke:#0b4884,stroke-width:1px
classDef container fill:#438dd5,color:#fff,stroke:#2e6295,stroke-width:1px
classDef containerdb fill:#438dd5,color:#fff,stroke:#2e6295,stroke-width:1px
classDef component fill:#85bbf0,color:#000,stroke:#5d82a8,stroke-width:1px
classDef planned fill:#c9d6e3,color:#333,stroke:#8a99a8,stroke-width:1px,stroke-dasharray: 5 5
```

Conventions that go with it:
- People are `(["..."])` rounded/stadium nodes with the `person` class;
  systems/containers/components are `["..."]` rectangles; databases are
  `[("...")]` cylinder nodes.
- Label every node with its C4 kind in the text itself — `<b>Name</b><br/>[Container: tech]<br/>description`
  — since flowchart nodes don't carry that metadata natively the way real
  C4 diagram types do.
- Group a system's own containers in a named `subgraph`; group anything
  planned-but-not-built in a separate subgraph styled `planned` (dashed,
  muted) with dotted (`-.->`) relationship arrows into/out of it.
- **Never use a semicolon inside diagram text**, in any diagram type, not
  just flowcharts. It's a real, silent-until-render parse trap: Mermaid's
  `sequenceDiagram` grammar treats `;` as a statement terminator, so
  `A->>B: Write response; status=X` truncates mid-message and fails to
  parse on whatever follows the semicolon. Use a comma or "and" instead.

## 4. Validate every diagram before calling it done

Don't trust that a diagram "looks right" in the markdown source — Mermaid
diagrams routinely have silent-until-rendered parse errors (see the
semicolon trap above) and layout problems that are invisible in the raw
text. Actually render every block:

```bash
npx -y @mermaid-js/mermaid-cli --version   # confirms mmdc works via npx, no global install needed
```

Then extract each ` ```mermaid ` block from the file into its own `.mmd`
file and render it:

```python
import re
content = open('architecture/architecture.md').read()
blocks = re.findall(r'```mermaid\n(.*?)```', content, re.DOTALL)
for i, b in enumerate(blocks):
    open(f'block_{i}.mmd', 'w').write(b)
```

```bash
for f in block_*.mmd; do npx -y @mermaid-js/mermaid-cli -i "$f" -o "${f%.mmd}.svg"; done
```

Any block that errors prints the exact parse failure (line/column) — fix
it in the source markdown, not just the extracted copy, and re-run. Once
everything parses, render the Context and Container diagrams (the
densest ones, most likely to have layout problems even when they parse) to
PNG at a decent width and actually look at them with the Read tool —
confirm no overlapping labels, no arrows crossing through box interiors,
before treating the file as finished. Record in the doc's own intro that
this validation was done, so the next reader trusts the diagrams without
re-checking.
