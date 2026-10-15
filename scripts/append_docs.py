"""Append the Task 9 System reference to harness.md and log Tasks 9-10 prompts."""

from pathlib import Path

HW5 = Path(__file__).resolve().parent.parent

HARNESS = """

---

# System reference

Everything in this assignment, in one place.

## Tables (`data/campus_customs_new.db`)

| Table | Rows | What it holds | Who writes it |
|---|---|---|---|
| `inventory` | 10 | Units on hand per `(sku, size)`, with aisle | `adjust_stock` |
| `pricing` | 4 | `unit_cost` and `list_price` per SKU — the margin floor | read only |
| `tickets` | 3 | The work queue; mixed type, with links to invoices and leases | `resolve_ticket` |
| `invoices` | 1 | Vendor bills: amount, due date, paid status | `record_payment` |
| `vendors` | 3 | Suppliers, specialty, `lead_days` | read only |
| `leases` | 1 | The authority on rent: landlord, amount, next due | read only |
| `cash_accounts` | 1 | The spending ceiling, with the date it was accurate | `record_payment` |
| `payments` | 0 → 2 | Append-only ledger of money that moved, with approver | `record_payment` |
| `desk` | 1 | `date_today` (the only clock) and the shared notes scratchpad | `post_desk_note` |

## MCP tools (10, server `campus-customs`)

| Tool | Kind | Tables |
|---|---|---|
| `check_stock` | read | `inventory` |
| `get_price_and_margin` | read | `pricing` |
| `get_cash_and_obligations` | read | `cash_accounts`, `invoices`, `vendors`, `leases`, `payments`, `desk` |
| `list_open_tickets` | read | `tickets`, `desk` |
| `get_ticket` | read | `tickets` + linked `inventory`, `pricing`, `invoices`, `vendors`, `leases` |
| `find_vendor` | read | `vendors`, `invoices` |
| `record_payment` | **write** | `payments`, `cash_accounts`, `invoices` |
| `adjust_stock` | **write** | `inventory` |
| `resolve_ticket` | **write** | `tickets` |
| `post_desk_note` | **write** | `desk` |

## The five agents

| Agent | Prompt | Tools it can see | Cannot do |
|---|---|---|---|
| **boss** | `backend/prompts/boss.md` | `list_open_tickets`, `get_ticket`, `resolve_ticket`, `post_desk_note`, plus four delegation tools | Check stock, quote a price, or pay — it must delegate |
| **inventory** | `inventory.md` | `check_stock`, `find_vendor`, `adjust_stock`, `get_ticket`, `post_desk_note` | Touch money |
| **accounting** | `accounting.md` | `get_cash_and_obligations`, `get_price_and_margin`, `record_payment`, `get_ticket`, `post_desk_note` | Change stock |
| **facilities** | `facilities.md` | `get_cash_and_obligations`, `get_ticket`, `post_desk_note` | **Pay** — it verifies rent, accounting settles it |
| **customer_service** | `customer_service.md` | `get_ticket`, `check_stock`, `get_price_and_margin`, `post_desk_note` | Move money or stock |

## API routes (`backend/main.py`, port 8000)

| Route | What it does |
|---|---|
| `GET /` | Desk dashboard control page |
| `GET /api/tickets` | All tickets with `is_open` and an open/resolved state |
| `POST /api/run` | Dispatches the team to a random or named ticket; returns a `run_id` at once |
| `GET /api/run/{run_id}` | Status and result of a run |
| `POST /api/tickets/{id}/resolve` | Closes a ticket by hand, with a required note |
| `GET /api/events` | Agent activity from the audit trail: who spoke, what they said, tools used |
| `POST /api/approve` | Executes a payment or purchase after a human clicks approve |
| `GET /api/balance` | Checking balance with obligations and what remains |
| `POST /api/reset` | Restores the working DB from the pristine pack; audit trail preserved |
| `GET /api/health` | Server plus MCP connectivity |

## Dashboard (`frontend/`, port 5173)

React + Vite + TypeScript in three columns: **queue** (open above closed), **work**
(ticket, agent roster, live transcript), **money** (balance meter, approvals). Each agent
has its own colour and glyph; the boss renders as a full-width solid-navy lane because it
is the only one that decides. Runs are asynchronous — the board polls the audit trail
every 1.2s, so the desks are visible while they work rather than only once they finish.
Full rationale in `output/design.md`.

## Safety

**Enforced in code** by the MCP write tools, so neither an agent nor a human approval can
bypass them: no overdraft (`insufficient_funds`), no double payment (`already_paid`),
exact amount only (`amount_mismatch`), named approver required (`no_approver`), stock
cannot go negative (`would_go_negative`), resolution notes required, and payments commit
as a single transaction.

**Enforced by structure:** per-desk tool filtering (`DESK_TOOLS`), and verification split
from payment — facilities establishes what rent is owed and has no payment tool at all.

**Enforced by budget:** 26 model requests / 36 tool calls / 220k tokens per ticket, shared
across the boss and every desk it consults; 600k tokens per shift; 4 delegations per
ticket. Every tool call and every refusal is written to `output/audit_trail.json`.

**Proof from the recorded shift of 2026-08-31:** all three agent runs moved **$0.00** and
escalated. The $3,240.00 that eventually moved was released by a named human. A
human-approved $500.00 payment against the $840.00 invoice was still refused, and so was a
repeat payment of the same invoice.
"""

PROMPTS = """
## Task 9 — Full shift, resolved tickets, cash reconciliation

9. > for task9, reset data/campus_customs_new.db to start clean. make a note of the beginning checking balance. run all tickets until each is resolved. open output/desk_tickets.html and on each tab fill the actual sections with which agents worked, what they delegated, and tools used. keep expected section as is. on cash tab itemeize the money by: beginnig reset checking balance, how cash changed for each ticket resolved and why  (which purchase plus amount), ending checking balance that matches cash_Accounts. correct cash amount is KEY!!!!!!!!!!! for each ticket use output/resolved_ticket.json save id, final status, short outcome, each agent's contributions, and any manual approvals. for each resolved ticket, in output/resolved_board.html have a page that can be double clicked for a screenshot of  React board. append runs in output/audit_trail.json. write tables, mcp tools, 5 agents, api  routes, dashboard, and safety in harness file

**Produced:** reset to a $3,400.00 opening balance; all three tickets run and driven to
`resolved` with a closing balance of **$160.00** matching `cash_accounts`; Actual sections
and an itemised Cash tab filled in `output/desk_tickets.html` (Expected sections left
untouched); `output/resolved_ticket.json`; `output/resolved_board.html` with double-click
screenshots in `output/resolved_board_images/`; `scripts/fill_desk_tickets.py`; and a
**System reference** section in `output/harness.md` covering tables, MCP tools, the five
agents, API routes, the dashboard and safety. Also fixed `get_cash_and_obligations`, which
kept reporting rent as owed after it had been paid because `leases.next_due` never
advances.

---

## Task 10 — Reflections

10. > for task 10 open output/desk_tickets.html and for reflection tab include: how would you evaluate agent ticket performance and why, how is actual vs expected plan different for each ticket, how and why would one agent with tools been simiplier, describe 3 new problems the company might have that our tools could solve, and have 3 new problems we couldnt solve and explain which tools/agents would be needed to do that. tie every answer to this app and the 3 tickets ran. have ticket and cash tabs on same page for evidence. DO NOT BE GENERIC!!!!!

**Produced:** the Reflections tab in `output/desk_tickets.html` — a six-measure evaluation
rubric scored against this shift, a per-ticket actual-vs-expected comparison including the
two predictions that were wrong and why, the case that one agent would have been simpler
(evidenced by the duplicate `get_cash_and_obligations` call on ticket 102), three problems
the existing tools already solve, and three that need new tables and new desks; plus
`scripts/fill_reflections.py`

---
"""


def main() -> None:
    (HW5 / "output" / "harness.md").open("a", encoding="utf-8").write(HARNESS)
    (HW5 / "AI_prompts.md").open("a", encoding="utf-8").write(PROMPTS)
    print("harness System reference appended; Tasks 9 and 10 logged")


if __name__ == "__main__":
    main()
