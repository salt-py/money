# Debt avalanche payoff planner

**Status:** Done

## Summary

`money debt` tracks each debt (credit cards, an overdraft, a store credit
line) with its balance/APR/minimum payment, and `debt plan` simulates an
avalanche payoff (highest effective APR first, re-evaluated every month)
to answer "how do I become debt free from here."

## What shipped

- `src/money/debt.py`: `get_tracked_debt_accounts()`, `load_debts()` /
  `save_debts()` (`config/debt.yaml`, gitignored), `effective_apr(debt,
  on_date)`, `simulate_avalanche(debts, extra_monthly, as_of, max_months)`.
- `money debt setup` (interactive entry per debt), `money debt show`,
  `money debt plan [--extra AMOUNT]` (month-by-month simulation with
  compounding interest, prints a payoff timeline).
- Promotional-rate support: a debt can have a 0%-intro-period end date,
  after which `effective_apr` switches to the real rate -- the simulation
  re-targets "highest effective APR" every month, so a promo expiring
  mid-plan correctly changes which debt gets the extra payment.

## Key decisions

- **Avalanche (highest APR first), not snowball (smallest balance
  first).** Minimizes total interest paid, at the cost of potentially
  slower "wins" on any single balance -- the right trade-off for a
  from-first-principles debt-free calculation rather than one optimized
  for psychological momentum.
- **APR target is re-evaluated monthly, not fixed at plan start.** A
  promotional 0% rate ending partway through the plan needs the simulation
  to notice the effective APR changed and re-target -- calculating once
  up front would keep paying down the (temporarily) cheapest debt past
  the point it's actually cheapest.
- **`config/debt.yaml` is gitignored** -- real balances and APRs, same
  treatment as `config/budget.yaml`.
