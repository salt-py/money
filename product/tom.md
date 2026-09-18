# Tom

**Core need:** Find and cut wasted recurring spend.

Tom suspects he's bleeding money on subscriptions he signed up for once
and forgot about, or that quietly raised their price — but they're spread
across a debit card and a couple of credit cards, so there's no single
place he can look to see them all at once. He doesn't want to manually
audit months of statements line by line; he wants the tool to notice
what's recurring on his behalf.

## Useful features

- ✅ `config/rules.yaml` categorization with labels — a recurring payee
  can already be tagged clearly once identified.
- 🔲 Recurring-payment detection — flag transactions that repeat at a
  similar amount on a roughly regular cadence, without needing a manual
  rule written for each one first.
- 🔲 A dedicated `report subscriptions` view — total recurring spend,
  grouped by payee, sorted by cost.
- 🔲 A "haven't seen this in N months" flag — a subscription that seems
  to have silently stopped, or whose amount has changed, worth a second
  look.
