# Ben

**Core need:** A simple "am I doing okay?" answer, no CLI expertise
required.

Ben signed up with good intentions but finds a dozen subcommands
intimidating. He doesn't want to learn the difference between
`report net-worth`, `report spending`, and `report discretionary` — he
wants to run one thing and get a plain answer about whether things are
fine or not. The gap between "the data is all there" and "I know what to
actually type" is the whole problem for Ben.

## Useful features

- ✅ `money categories` / `money categorize` — a gentle, guided on-ramp
  for getting the basics (categories, rules) set up in the first place.
- 🔲 A single `money checkup` (or `summary`) command bundling the handful
  of numbers that matter most — net worth, this month vs. budget, any
  large Uncategorized backlog — into one readable block. Same underlying
  need as Marcus's "one place to look," but framed as a guided default
  rather than a report he has to know to ask for.
- 🔲 Guided first-run setup — a wizard-style `money init` that walks
  through copying the `.example` configs and running the first import,
  instead of expecting the README to be read start to end.
- 🔲 Plain-language framing on numbers ("you're on track" / "a bit over
  this month") alongside the raw figures, not instead of them.
