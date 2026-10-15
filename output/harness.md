# Harness — Campus Customs Operations Database

This file documents the data the agent works from: every table in
`data/campus_customs.db`, every field in those tables, and why each one matters to an
agent running the shop's front desk.

- **Source (read-only):** `data/campus_customs.db` — the pristine data pack. Never written to.
- **Working copy (read/write):** `data/campus_customs_new.db` — byte-identical copy made with
  SQLite's backup API; this is the database the agent updates.
- **"Today" in this dataset:** `2026-08-31` (from `desk.date_today` and `cash_accounts.date`).
  Every due-date judgment the agent makes is relative to this date, **not** the real clock.

---

## The shop in one paragraph

Campus Customs is a small Yale apparel and gift shop on Chapel Street. It holds four
products across ten size-level stock rows, buys from three vendors, rents its space, and
works from a ticket queue. At the current snapshot there are **three open tickets**, one
**overdue vendor invoice**, **rent due in two days**, and **$3,400** in the checking
account. The agent's job is to read this state, decide what to do, and record what it did.

---

## Data model at a glance

```
vendors ──< invoices ──┐
                       ├──< tickets >── leases
inventory ── pricing   ┘
   (sku)      (sku)

payments ──> invoices | leases   (polymorphic via kind + ref_id)
payments ──> cash_accounts       (via account name)

desk = the agent's scratchpad and clock
```

Three foreign keys are declared in the schema: `invoices.vendor_id → vendors.id`,
`tickets.invoice_id → invoices.id`, `tickets.lease_id → leases.id`. The rest of the joins
(`inventory.sku ↔ pricing.sku`, `payments.ref_id ↔ invoices/leases`,
`payments.account ↔ cash_accounts.name`) are **conventions, not constraints** — the
database will not stop the agent from writing a payment that points at nothing, so the
agent has to validate those links itself.

---

## `inventory` — what is physically on the shelf

**Why it matters to the agent:** this is the single source of truth for whether the shop
can actually fill an order. The agent must never promise, reserve, or sell a unit that
isn't counted here. Because the primary key is `(sku, size)`, stock is tracked per size —
a product can be in stock overall and still be unavailable in the size a customer wants,
which is exactly the situation in ticket 101.

| Field | Type | Why the agent needs it |
|---|---|---|
| `sku` | TEXT, PK part 1 | The join key to `pricing` and the product reference on tickets. Identifies the product line, not the sellable unit. |
| `name` | TEXT, required | Human-readable product name. What the agent says back to a customer instead of a raw SKU. |
| `size` | TEXT, PK part 2 | The other half of a sellable unit. `S`/`M`/`L`/`XL` for apparel, `OS` (one size) for hats and mugs. Order fulfilment is decided at this granularity. |
| `qty` | INTEGER, required | Units on hand. The hard ceiling on any fulfilment or bulk-order decision, and the trigger for a reorder. `0` means out of stock — the agent says so rather than back-ordering silently. |
| `location` | TEXT, required | Physical aisle (`Aisle A`–`Aisle D`). Lets the agent tell staff where to pick the item, turning an answer into an actionable instruction. |

**Current state:** 10 rows / 4 SKUs. Two are at zero — `CC-TEE-WHITE` size `S` and
`CC-MUG-CREST` — and the tee in `S` is the one an open customer ticket is asking for.

---

## `pricing` — cost and list price per product

**Why it matters to the agent:** this is the only place margin can be computed, so it is
the guardrail on every discount conversation. `list_price` is what the agent may quote;
`unit_cost` is the floor it must not quote below. Pricing is keyed by `sku` alone, so all
sizes of a product share one price — the agent should not invent size-based pricing.

| Field | Type | Why the agent needs it |
|---|---|---|
| `sku` | TEXT, PK | Joins to `inventory`. One price row per product line. |
| `unit_cost` | REAL, required | What the shop paid. The margin floor: a discount that lands at or under this number loses money, so the agent needs it to refuse or escalate a bad ask. |
| `list_price` | REAL, required | The published sell price. The number the agent quotes, and the baseline any discount percentage is measured against. |

**Current state:** hoodie $22 → $58, tee $8 → $28, cap $6 → $22, mug $3.50 → $14.
Margins run 62–75%, which is the headroom the agent has to work with on ticket 103.

---

## `tickets` — the agent's work queue

**Why it matters to the agent:** this is the inbox and the reason the agent is running at
all. Every task enters here, and `status` is how the agent reports that it finished. The
table is deliberately **mixed-type** — one row can be a customer order, a landlord notice,
or a discount request — so the agent has to branch on `type` and read only the fields
relevant to that type. The nullable link columns are what connect a ticket to the record
it is about.

| Field | Type | Why the agent needs it |
|---|---|---|
| `id` | INTEGER, PK | Stable handle for the task, used when logging what was done. |
| `type` | TEXT, required | The router. `customer_order`, `rent_notice`, `price_override` — each needs a different procedure, different tables, and a different approval bar. |
| `requester` | TEXT, required | Who is asking. Separates a customer from the landlord from a student org, which changes both tone and authority to act. |
| `subject` | TEXT, required | One-line summary for triage before reading `notes`. |
| `sku` | TEXT, nullable | Product the ticket concerns; joins to `inventory`/`pricing`. Null on tickets that aren't about a product. |
| `size` | TEXT, nullable | With `sku`, pins the exact stock row to check. Null means the request isn't size-specific. |
| `qty` | INTEGER, nullable | Units requested. Checked against `inventory.qty` before anything is promised. |
| `lease_id` | INTEGER, nullable, FK → `leases.id` | Links a rent notice to the lease it concerns, so the agent verifies the amount against the lease instead of trusting the email. |
| `invoice_id` | INTEGER, nullable, FK → `invoices.id` | Links a ticket to a vendor bill — e.g. the reprint already ordered to cover an out-of-stock item. Tells the agent work is already in flight. |
| `status` | TEXT, required | `open` vs resolved. The agent's completion signal and the guard against doing the same job twice. |
| `notes` | TEXT, nullable | Free-text detail — the ask in the requester's own words. Carries the specifics (quantities, deadlines) that the structured columns don't. |
| `created_at` | TEXT, required | ISO 8601 with offset (`-04:00`). Orders the queue and, against `desk.date_today`, shows how long something has been waiting. |

**Current state — the three open tickets:**

| # | Type | Requester | The ask | The catch the agent must notice |
|---|---|---|---|---|
| 101 | `customer_order` | Tauhid Zaman | 1 × `CC-TEE-WHITE` size `S` | Stock is **0**. Invoice 501 is already a rush reprint of this exact item, so a reorder would be a duplicate. |
| 102 | `rent_notice` | Elm City Properties | Rent due | Verify $2,400 against lease 1 rather than the email; due `2026-09-02`, two days out. |
| 103 | `price_override` | Yale AI Club | 20 × `CC-HOOD-NAVY` size `M`, bulk discount | Only **8** in stock, not 20. Any discount must stay above the $22 unit cost. |

---

## `invoices` — money owed to vendors

**Why it matters to the agent:** the payables side of the ledger. The agent reads it to
know what is owed, to whom, and whether it is late, and to avoid re-ordering something
already on order. `status` prevents double payment.

| Field | Type | Why the agent needs it |
|---|---|---|
| `id` | INTEGER, PK | The `ref_id` a payment points back to. |
| `vendor_id` | INTEGER, required, FK → `vendors.id` | Who gets paid, and the route to that vendor's `lead_days`. |
| `amount` | REAL, required | The authoritative amount owed — checked against cash before approving anything. |
| `due_date` | TEXT, required | Compared with `desk.date_today` to rank urgency and spot overdue bills. |
| `status` | TEXT, required | `open` vs paid. The duplicate-payment guard: the agent pays only `open` invoices. |
| `description` | TEXT, nullable | What the bill covers. Here it is what reveals invoice 501 is the reprint for the out-of-stock tee, tying the money to the inventory gap. |

**Current state:** one invoice — #501, $840, Bulldog Print Co, "Rush reprint
CC-TEE-WHITE S", due `2026-08-28`, still `open`. Against today's `2026-08-31` it is
**three days overdue**.

---

## `vendors` — who the shop buys from

**Why it matters to the agent:** restocking is a timing promise, not just a purchase.
`lead_days` is the only data that lets the agent say *when* an out-of-stock item returns,
and `specialty` is how it picks the right supplier instead of guessing.

| Field | Type | Why the agent needs it |
|---|---|---|
| `id` | INTEGER, PK | Target of `invoices.vendor_id`. |
| `name` | TEXT, required | Who the agent names in a reply or a payment record. |
| `specialty` | TEXT, required | Routes a restock to a supplier that actually makes that category — apparel reprints vs. mugs and small goods vs. courier. |
| `lead_days` | INTEGER, required | Turnaround in days. Added to `desk.date_today` it produces a concrete restock date, which is what turns "out of stock" into a real answer for the customer. |

**Current state:** Bulldog Print Co (apparel reprint, 5 days), Elm City Gifts (mugs and
small goods, 3 days), QuickShip CT (local courier, 1 day). The tee reprint on invoice 501
is apparel → Bulldog Print Co → **5 days** out.

---

## `leases` — the shop's rent obligation

**Why it matters to the agent:** rent is the largest recurring outflow and the claim the
agent must verify independently. When a landlord emails asking for money, this table — not
the email — is the authority on how much is actually owed.

| Field | Type | Why the agent needs it |
|---|---|---|
| `id` | INTEGER, PK | Target of `tickets.lease_id` and of a rent `payments.ref_id`. |
| `space_name` | TEXT, required | Which space, for shops with more than one location. |
| `landlord` | TEXT, required | Cross-checked against `tickets.requester` to confirm the notice came from the actual landlord. |
| `monthly_rent` | REAL, required | The verified amount. If an emailed figure disagrees with this, the agent trusts this one and flags the difference. |
| `next_due` | TEXT, required | The real deadline, ranked against invoice due dates when cash is tight. |
| `notes` | TEXT, nullable | Lease-specific terms or exceptions. Currently empty. |

**Current state:** Chapel Street shop, Elm City Properties, $2,400/month, next due
`2026-09-02`. Ticket 102's requester matches the landlord on file, and the two-day window
is the pressure behind the cash decision below.

---

## `cash_accounts` — what the shop can actually spend

**Why it matters to the agent:** the spending ceiling. Every payment decision is bounded
by this balance, and this is the table that makes the current snapshot a real trade-off
rather than a formality.

| Field | Type | Why the agent needs it |
|---|---|---|
| `name` | TEXT, PK | Account identifier (`checking`); matches `payments.account`. |
| `balance` | REAL, required | Funds available. The hard constraint on paying the invoice, the rent, or both, and the number to decrement after a payment. |
| `date` | TEXT, required | When the balance was accurate. A balance is only trustworthy as of its date, so the agent should not treat a stale figure as current. |

**Current state:** `checking` holds **$3,400.00** as of `2026-08-31`. Against $840 overdue
plus $2,400 rent — **$3,240 total** — both can be covered, but only $160 is left
afterwards. That slim margin is why the agent should sequence payments and surface the
remaining balance rather than paying silently.

---

## `payments` — the audit trail the agent writes

**Why it matters to the agent:** this is the **primary write target**. Every other table
is mostly read; this one is where the agent's financial actions get recorded. It is
currently empty, so each row is evidence of something the agent chose to do. `approved_by`
is the accountability field — it records that money moved under a named authority, which
is what keeps an autonomous agent from spending without a trace.

| Field | Type | Why the agent needs it |
|---|---|---|
| `id` | INTEGER, PK | Payment identifier. |
| `kind` | TEXT, required | What is being paid (e.g. invoice vs. rent). With `ref_id` it forms a polymorphic pointer — `kind` says which table to look in. |
| `ref_id` | INTEGER, nullable | The id in that table (`invoices.id` or `leases.id`). Unenforced by the schema, so the agent validates it before writing. |
| `amount` | REAL, required | Amount paid. Must reconcile against the invoice or lease, and must be subtracted from `cash_accounts.balance`. |
| `account` | TEXT, required | Which account was drawn down; matches `cash_accounts.name`. |
| `paid_at` | TEXT, required | Payment timestamp, for ordering the ledger and proving a deadline was met. |
| `approved_by` | TEXT, required | Who authorised it. Required on every row — no payment exists without a named approver. |

**Current state:** empty. Nothing has been paid, including the overdue invoice.

---

## `desk` — the agent's clock and scratchpad

**Why it matters to the agent:** `date_today` is the authoritative "now" for this dataset.
Without it the agent would compare 2026 due dates against the real system clock and
misjudge every deadline. `notes` is working memory the agent can carry between runs.

| Field | Type | Why the agent needs it |
|---|---|---|
| `date_today` | TEXT, required | The reference date for all urgency math: overdue vs. upcoming, and the base for `lead_days` restock estimates. |
| `notes` | TEXT, nullable | Free-text scratchpad for context or hand-off between runs. Currently `NULL`. |

**Current state:** `2026-08-31`, no notes.

---

## Read and write surface

| Table | Agent access | Why |
|---|---|---|
| `inventory` | read; write on fulfilment/restock | `qty` drops when units are committed. |
| `pricing` | read | Margin floor; changing it would rewrite the guardrail. |
| `tickets` | read; write `status`/`notes` | Marking work complete is how the queue drains. |
| `invoices` | read; write `status` | Flipped to paid once a payment row exists. |
| `vendors` | read | Reference data — the shop's supplier list, not the agent's to edit. |
| `leases` | read | The authority on rent; the agent verifies against it, never adjusts it. |
| `cash_accounts` | read; write `balance` | Decremented by exactly the amount of each payment written. |
| `payments` | **append only** | The audit trail. Rows are added, never edited or deleted. |
| `desk` | read `date_today`; write `notes` | The date is given; the notes are the agent's own memory. |

All writes land in `data/campus_customs_new.db`. `data/campus_customs.db` stays pristine so
any run can be reset and compared against the original state.

---

# MCP Tools

Every agent in this assignment reaches the database through one FastMCP server,
`mcp_server/server.py` (server name: `campus-customs`), which reads
`data/campus_customs_new.db`. The tools issue only `SELECT` statements, have no defaults
and no fallbacks, and read the current date from `desk.date_today` rather than the system
clock. A record that is not on file returns `found = false` with an explicit explanation,
so an agent is never handed a plausible-looking guess.

## Coverage at a glance

| Tool | Tables read | Primary ticket | Also unlocks |
|---|---|---|---|
| `check_stock` | `inventory` | **101** — can we fill the tee order? | **103** — are there even 20 hoodies? |
| `get_price_and_margin` | `pricing` | **103** — how deep can the discount go? | **101** — the price to quote on the tee |
| `get_cash_and_obligations` | `cash_accounts`, `invoices`, `vendors`, `leases`, `payments`, `desk` | **102** — is the rent claim real and affordable? | **101** — the reprint is already on order |

---

## 1. `check_stock(sku, size=None, requested_qty=None)`

**Reads:** `inventory` — `sku`, `name`, `size`, `qty`, `location`.

**Returns:** one `StockRow` per matching size with `in_stock`, plus `can_fill` and
`shortfall` when `requested_qty` is supplied.

### Ticket 101 — Tauhid Zaman, 1 × `CC-TEE-WHITE`, size `S`

```
check_stock("CC-TEE-WHITE", "S", requested_qty=1)
-> found=True, qty=0, in_stock=False, can_fill=False, location="Aisle B"
   "Classic Bulldog Tee (CC-TEE-WHITE) size S is OUT OF STOCK: 0 on hand in Aisle B."
```

**Why this tool is the right instrument for this ticket:** the tee is not a
discontinued product — it has four size rows holding **10 units in total** (M=5, L=3,
XL=2). Any lookup that resolved stock at SKU level would correctly report "10 on hand"
and an agent would confirm an order the shop physically cannot fill. The size `S` row is
the only row that says `0`. Because `inventory`'s primary key is `(sku, size)` and this
tool queries at that same grain, the out-of-stock condition is impossible to miss:
`in_stock` and `can_fill` both come back `False` for the exact unit the customer asked
for. The `location` field (`Aisle B`) is what lets the agent's answer name where staff
would have picked it, and `requested_qty=1` makes the verdict explicit rather than
leaving the agent to compare numbers itself.

### Ticket 103 — Yale AI Club, 20 × `CC-HOOD-NAVY`, size `M`

```
check_stock("CC-HOOD-NAVY", "M", requested_qty=20)
-> qty=8, can_fill=False, shortfall=12
   "Basic Hoodie Big Yale (CC-HOOD-NAVY) size M has 8 on hand in Aisle A,
    short 12 of the 20 requested."
```

**Why this tool is the right instrument for this ticket:** ticket 103 presents itself as
a *pricing* question, and that framing is the trap. Before any discount is worth
discussing, the shop has to be able to supply the order — and it cannot. There are **8**
hoodies in M against a request for **20**, a shortfall of **12**. An agent that went
straight to `get_price_and_margin` would negotiate a bulk rate on twelve garments that do
not exist. Calling `check_stock` first converts the ticket from "what discount?" into
"8 now and 12 to reprint, then what discount?" — which is the question actually worth
answering.

---

## 2. `get_price_and_margin(sku, qty=1, proposed_unit_price=None)`

**Reads:** `pricing` — `sku`, `unit_cost`, `list_price`.

**Returns:** cost, list price, and full-price margin; plus, when `proposed_unit_price` is
given, a `PriceQuote` with the discount off list, the resulting per-unit margin, line
totals at `qty`, and an `above_cost` flag.

### Ticket 103 — Yale AI Club, bulk hoodie discount

```
get_price_and_margin("CC-HOOD-NAVY", qty=20, proposed_unit_price=35.00)
-> unit_cost=22.00, list_price=58.00, margin=36.00 (62.1%)
   quote: 39.7% off list, margin $13.00/unit, above_cost=True,
          line_total=$700.00, line_margin=$260.00

get_price_and_margin("CC-HOOD-NAVY", qty=20, proposed_unit_price=20.00)
-> quote: margin -$2.00/unit, above_cost=False, line_margin=-$40.00
   "...AT OR BELOW cost - this loses money."
```

**Why this tool is the right instrument for this ticket:** the Yale AI Club asked for "a
bulk discount" and named **no number**, so the agent has to produce one. `pricing` is the
only table in the entire schema that holds `unit_cost`, which makes it the only place a
discount floor can be established — nothing in `inventory`, `tickets`, or `invoices`
reveals what the shop paid. This tool turns that floor into a usable guardrail in two
ways. First, it reports the headroom directly: $22.00 cost against $58.00 list is
**$36.00 of margin per hoodie**, so the agent knows how much room it is working with
before it opens its mouth. Second, `proposed_unit_price` lets it test a specific figure
*before* committing to it in a reply — $35.00 clears cost with $13.00/unit, while $20.00
is flagged `above_cost=False` and would lose $40.00 across the order. Passing `qty=20`
prices the actual order rather than a single unit, which is the number that matters in a
bulk negotiation. The tool is also keyed by `sku` alone, matching the table, so it
structurally cannot invent a size-specific price for the M hoodies.

### Ticket 101 — the tee's price

Since the tee cannot ship today, any reply that offers to reserve or back-order it has to
quote a real figure. `get_price_and_margin("CC-TEE-WHITE")` returns **$28.00** list
against $8.00 cost. The agent quotes the table, not a remembered number.

---

## 3. `get_cash_and_obligations()`

**Reads:** `cash_accounts` (balances), `invoices` (unpaid bills), `vendors` (joined for
`lead_days` and `specialty`), `leases` (rent on file), `payments` (what has already been
paid), `desk` (`date_today`, for every overdue calculation).

**Returns:** a whole-position `CashPosition` snapshot. Takes no arguments.

### Ticket 102 — Elm City Properties, "shop rent due in 2 days"

```
get_cash_and_obligations()
-> as_of = "2026-08-31"                      (from desk.date_today)
   accounts: checking $3,400.00
   leases:   #1 Chapel Street shop, landlord "Elm City Properties",
             monthly_rent $2,400.00, next_due 2026-09-02, days_until_due = +2
   invoices: #501 Bulldog Print Co $840.00, due 2026-08-28,
             days_until_due = -3, is_overdue = True
   total_obligations $3,240.00 | remaining_if_all_paid $160.00
   can_cover_all = True | recorded_payments = 0
```

**Why this tool is the right instrument for this ticket:** the rent notice is an **email
that states no amount** — `tickets.notes` reads only "Email: shop rent due in 2 days." An
agent cannot pay a bill off an unverified claim, and this tool resolves the claim against
the ledger on three separate axes at once:

- **Is the requester genuine?** `leases.landlord` is `Elm City Properties`, which matches
  `tickets.requester` exactly. The notice came from the landlord actually on the lease.
- **Is the amount real?** The email never says. `leases.monthly_rent` is the authority:
  **$2,400.00**. This is the figure the agent pays, and if a notice ever disagrees with
  it, the lease wins.
- **Is the deadline real?** `next_due` is `2026-09-02`, and `days_until_due = +2`
  computed against `desk.date_today` (`2026-08-31`) — which corroborates the email's "in
  2 days". Had this been measured against the real system clock, the answer would have
  been wrong by years.

The decisive reason this tool returns cash *and* obligations together, rather than a bare
balance lookup, is the competing claim on the same money. A balance check alone would
report $3,400.00 against $2,400.00 rent and conclude "comfortably affordable, pay it" —
while silently ignoring the **$840.00 invoice that is already three days overdue**. Both
obligations draw on the one `checking` account. Seen together, the real position is
$3,240.00 of total obligations against $3,400.00 of cash, leaving **$160.00**. That is
still `can_cover_all = True`, but it is a sequencing decision with almost no buffer, not
a rubber stamp — and the agent can only see that because the tool hands it both sides.
`recorded_payments = 0` confirms nothing has been paid yet, so neither bill is at risk of
being paid twice.

### Ticket 101 — why the tee order is already half-solved

The same call also carries the fact that resolves the other half of ticket 101:

```
invoice #501  "Rush reprint CC-TEE-WHITE S"
              vendor: Bulldog Print Co (apparel reprint, lead_days = 5)
              $840.00, due 2026-08-28, is_overdue = True
```

**Why this matters specifically:** ticket 101 carries `invoice_id = 501`, and that
invoice's `description` names the exact SKU and size the customer is waiting for. A
restock for this order **has already been placed**. An agent that saw only "size S, qty
0" would helpfully order a second reprint and commit the shop to another $840.00 it
cannot afford. The vendor join supplies `lead_days = 5`, which is the only data in the
database capable of turning "out of stock" into a date the customer can be told.

It also exposes a coupling the two tickets do not state on their own: the reprint that
ticket 101 depends on sits behind an invoice that is **overdue and unpaid**. A vendor owed
$840.00 for three days is not reliably going to rush the job. Paying invoice 501 is
plausibly what unblocks the customer order — a connection that is only visible because
this tool reads `invoices`, `vendors`, and `cash_accounts` in a single snapshot.

> **One caveat on the ETA.** `expected_delivery_date` is *derived* as
> `due_date + vendor_lead_days` (2026-08-28 + 5 = 2026-09-02). It is an estimate computed
> from recorded values, not a shipping date the vendor has confirmed — the database holds
> no such field. An agent should present it as an estimate and say so.

---

## The anti-hallucination contract

These guarantees are what let an agent quote tool output directly:

| Guarantee | How it is enforced |
|---|---|
| No invented products | Unknown SKU returns `found = false` and a summary saying the record does not exist. |
| No invented sizes | A SKU on file with an unstocked size returns `found = true`, zero rows, and lists the sizes that *do* exist (`CC-HAT-BLUE` size `XXL` → "Sizes on file: OS"). |
| No invented prices | A SKU with no `pricing` row returns `found = false` — no price may be quoted for it at all. |
| No invented dates | "Today" is read from `desk.date_today`; `db.today()` raises rather than falling back to the system clock if the value is missing. |
| No invented money | Every balance, amount, and total is summed from rows actually selected. |
| Case-insensitive, not fuzzy | `cc-mug-crest` resolves to `CC-MUG-CREST`, but a near-miss SKU is a miss — the tools never guess at what was meant. |

---

# The full MCP tool list

Task 5 added seven tools so the team can **work** tickets, not only read about them.
All ten live on the one `campus-customs` server and are the agents' only route to shop
data.

| # | Tool | Tables read | Tables written | Added |
|---|---|---|---|---|
| 1 | `check_stock` | `inventory` | — | Task 3 |
| 2 | `get_price_and_margin` | `pricing` | — | Task 3 |
| 3 | `get_cash_and_obligations` | `cash_accounts`, `invoices`, `vendors`, `leases`, `payments`, `desk` | — | Task 3 |
| 4 | `list_open_tickets` | `tickets`, `desk` | — | Task 5 |
| 5 | `get_ticket` | `tickets`, `inventory`, `pricing`, `invoices`, `vendors`, `leases`, `desk` | — | Task 5 |
| 6 | `find_vendor` | `vendors`, `invoices` | — | Task 5 |
| 7 | `record_payment` | `payments`, `invoices`, `leases`, `cash_accounts`, `desk` | `payments`, `cash_accounts`, `invoices` | Task 5 |
| 8 | `adjust_stock` | `inventory` | `inventory` | Task 5 |
| 9 | `resolve_ticket` | `tickets` | `tickets` | Task 5 |
| 10 | `post_desk_note` | `desk` | `desk` | Task 5 |

### What the new tools are for

**`list_open_tickets`** — the work queue, and the first call of any shift. Reads
`tickets` for rows with `status = 'open'`, and `desk.date_today` to age each one.

**`get_ticket`** — one ticket plus every record it links to, resolved in a single call.
It reads `tickets` for the row, then follows `sku`/`size` into `inventory` and
`pricing`, `invoice_id` into `invoices` (joined to `vendors`), and `lease_id` into
`leases`. This is the team's main token saving: one call instead of four, and it is why
the boss's first move on every ticket is `get_ticket`.

**`find_vendor`** — suppliers filtered by `specialty`, with `lead_days` for restock
dates. It also counts each vendor's unpaid bills from `invoices`, because a supplier
owed money may not rush a job — which is exactly the situation on ticket 101.

**`record_payment`** — the only way money leaves the shop. Writes a row to `payments`,
decrements `cash_accounts.balance`, and flips `invoices.status` to paid, in one
transaction. Validates against `invoices`/`leases` for the amount owed and against
`payments` for prior settlement. Its refusals are listed under Safety guardrails below.

**`adjust_stock`** — commits units out or books a delivery in, against `inventory`.
Refuses any change that would drive a count below zero.

**`resolve_ticket`** — closes a ticket with a status and a resolution note, appending
the note to `tickets.notes` rather than replacing it.

**`post_desk_note`** — the shared workspace. Appends one timestamped, attributed line
to `desk.notes`, so one desk can leave a finding for another and a shift can hand off
to the next. Appends only; nothing already written is overwritten.

---

# The agent team

Five Pydantic AI agents in `backend/`, reaching the shop **only** through the MCP
server. Nothing in `backend/` imports sqlite3 or opens the database — `mcp_client.py`
is the single bridge, so there is no second tools layer that could bypass the write
guardrails.

```
          boss  (backend/prompts/boss.md)
            │   reads the queue, routes, decides, closes tickets
            ├── inventory          stock, shortfalls, restock timing
            ├── accounting         cash, invoices, margins, payments
            ├── facilities         lease, rent, landlord claims
            └── customer_service   the reply the requester receives
```

Delegation is implemented as four tools on the boss — `ask_inventory`,
`ask_accounting`, `ask_facilities`, `ask_customer_service`. Each runs the specialist
agent and returns a typed `SpecialistReport`.

## Each agent, its tools, and the tables behind them

### boss — shift manager
*Prompt:* `backend/prompts/boss.md`  ·  *Output:* `TicketResolution`

| Tool | Tables used |
|---|---|
| `list_open_tickets` | `tickets`, `desk` |
| `get_ticket` | `tickets`, `inventory`, `pricing`, `invoices`, `vendors`, `leases` |
| `resolve_ticket` | `tickets` (write) |
| `post_desk_note` | `desk` (write) |
| `ask_inventory` / `ask_accounting` / `ask_facilities` / `ask_customer_service` | delegation — no direct table access |

The boss has no stock, pricing, or payment tools at all. It cannot check a quantity or
move money itself; it must delegate. That keeps one agent from doing everything badly
and makes each desk's reasoning separately auditable.

### inventory
*Prompt:* `backend/prompts/inventory.md`  ·  *Output:* `SpecialistReport`

| Tool | Tables used |
|---|---|
| `check_stock` | `inventory` |
| `find_vendor` | `vendors`, `invoices` |
| `adjust_stock` | `inventory` (write) |
| `get_ticket` | `tickets` + linked `inventory`, `pricing`, `invoices`, `leases` |
| `post_desk_note` | `desk` (write) |

### accounting
*Prompt:* `backend/prompts/accounting.md`  ·  *Output:* `SpecialistReport`

| Tool | Tables used |
|---|---|
| `get_cash_and_obligations` | `cash_accounts`, `invoices`, `vendors`, `leases`, `payments`, `desk` |
| `get_price_and_margin` | `pricing` |
| `record_payment` | `payments`, `cash_accounts`, `invoices` (write); reads `leases`, `desk` |
| `get_ticket` | `tickets` + linked records |
| `post_desk_note` | `desk` (write) |

**The only desk that can pay.** No other agent can see `record_payment`.

### facilities
*Prompt:* `backend/prompts/facilities.md`  ·  *Output:* `SpecialistReport`

| Tool | Tables used |
|---|---|
| `get_cash_and_obligations` | `leases`, `cash_accounts`, `invoices`, `vendors`, `payments`, `desk` |
| `get_ticket` | `tickets` + linked `leases` |
| `post_desk_note` | `desk` (write) |

Deliberately has **no payment tool**. It verifies a rent claim against the lease and
hands the verified figure to accounting. Separating the desk that confirms a debt from
the desk that settles it means no single agent can both invent an obligation and pay it.

### customer_service
*Prompt:* `backend/prompts/customer_service.md`  ·  *Output:* `SpecialistReport`

| Tool | Tables used |
|---|---|
| `get_ticket` | `tickets` + linked records |
| `check_stock` | `inventory` |
| `get_price_and_margin` | `pricing` |
| `post_desk_note` | `desk` (write) |

Read-only on money and stock. It can confirm a figure before stating it to a customer,
but it cannot commit the shop to anything.

---

# Safety guardrails

Three things need protecting: the customer, the shop's money, and the token budget.
The rules below are grouped by which. **Guardrails marked (code) are enforced in
`mcp_server/`, not in a prompt** — an agent cannot talk its way past them, because the
tool returns `ok: false` and commits nothing.

## Protecting customers

| Guardrail | Where | What it prevents |
|---|---|---|
| Stock checked at `(sku, size)` (code) | `check_stock` | Promising a size that is out of stock because the product looks available overall — ticket 101's exact trap. |
| `found: false` instead of a guess (code) | all read tools | Inventing a product, size, or price that does not exist. |
| Sizes on file listed on a miss (code) | `check_stock` | A near-miss being silently resolved to the wrong item. |
| No clock access (code) | `db.today()` | Quoting a delivery date computed from the wrong year. `today()` raises rather than falling back to the system clock. |
| Restock dates labelled estimates | `inventory.md`, harness | A derived `due_date + lead_days` being passed to a customer as a confirmed ship date. |
| Customer service cannot write money or stock (code) | `DESK_TOOLS` filter | The desk that talks to customers committing the shop to something it has not agreed. |
| `facts_used` required on every claim | `SpecialistReport` | A number appearing in a customer message that no tool ever returned. |

## Protecting the shop's money

| Guardrail | Where | What it prevents |
|---|---|---|
| **No overdraft** (code) | `record_payment` | Any payment that would leave a negative balance. Refused with `insufficient_funds`; verified by test. |
| **No double payment** (code) | `record_payment` | Paying an invoice already marked paid, or any obligation with an existing payment row. Refused with `already_paid`. |
| **Exact amount only** (code) | `record_payment` | Paying what a notice claims rather than what the ledger says. A mismatch is refused with `amount_mismatch`. |
| **Named approver required** (code) | `record_payment` | Money moving with nobody accountable. Empty `approved_by` is refused. |
| **Single transaction** (code) | `record_payment` | A ledger where cash was debited but the invoice never marked paid. |
| **Stock cannot go negative** (code) | `adjust_stock` | Overselling to make a shortfall disappear. |
| **Only accounting can pay** (code) | `DESK_TOOLS` filter | Four agents with independent authority to spend. |
| **Verification split from payment** | facilities vs accounting | One agent both confirming a debt and settling it. |
| Cost floor on every discount | `get_price_and_margin`, `accounting.md` | Agreeing a price at or below `unit_cost`. `above_cost` is computed, not estimated. |
| Escalate when cash goes thin | `boss.md`, `accounting.md` | Draining the account to $160 on an agent's own authority. On the recorded run this fired: the team escalated both money tickets and moved **$0.00**. |
| Every write audited (code) | `mcp_client.process_tool_call` | An unexplained balance change. Refusals are logged as `guardrail` records too. |

## Protecting the token budget

| Guardrail | Where | What it prevents |
|---|---|---|
| **Shared usage across delegation** (code) | `usage=ctx.usage` in `_consult` | A four-desk ticket costing four separate budgets. Boss and every desk draw on one. |
| **Per-ticket ceilings** (code) | `TICKET_LIMITS` | 26 model requests, 36 tool calls, 220k tokens per ticket — covering all desks together. |
| **Shift budget** (code) | `SHIFT_TOKEN_BUDGET` | A runaway queue. The loop stops at 600k tokens or 10 tickets and records why. |
| **Delegation cap** (code) | `max_delegations_per_ticket` (4) | A boss re-asking the same desk in a loop. The 5th call returns a refusal, not an agent run. |
| **Least-privilege tool lists** (code) | `DESK_TOOLS` filter | Every agent paying to read all ten tool schemas on every request. Each desk loads 3–5. |
| `get_ticket` returns linked records | `get_ticket` | Four round trips to understand one ticket. |
| Prompts forbid re-reading | `_shared.md` | Re-fetching a value already in context. |
| Audit entries are length-capped (code) | `audit._clip` | The trail growing into a second copy of the database. |

### Observed cost

The recorded full run (`run-af9fd40ea741`) handled all three tickets in **85,390 tokens
across 29 model requests and 20 MCP tool calls** — roughly 28k tokens per ticket
including every delegation.

---

# Audit trail

`output/audit_trail.json` is **JSON Lines**: one JSON object per line, opened in append
mode only. Re-running the team adds to the history; it never wipes it. The file
currently holds records from more than one run, which is the intended behaviour.

JSON Lines rather than a JSON array because an array must be read, parsed, extended and
rewritten on every append — so a crash mid-write can truncate the whole history, and two
writers can lose each other's records.

| Event | Records |
|---|---|
| `run_start` / `run_end` | Approver, limits in force, stop reason, totals, escalations |
| `ticket_start` / `ticket_end` | Type, requester, disposition, decision, desks consulted, money moved |
| `delegation` / `delegation_result` | Which desk was asked what, and the finding, facts, and actions it returned |
| `tool_call` | Agent, tool, arguments, result summary, `ok`, `is_write`, duration, refusal reason |
| `guardrail` | A safety rule firing — a refused write, a cap reached, a dry run |
| `usage` | Tokens and requests, attributed per agent per ticket |
| `error` | Exceptions, with the ticket that caused them |

Every MCP call is captured by the `process_tool_call` hook in `backend/mcp_client.py`,
so a tool call cannot happen without a record of it.

---

# FastAPI routes

`backend/main.py`. Start it from the `backend/` folder:

```
uvicorn main:app --reload --port 8000
```

The backend then serves at **http://localhost:8000**.

Every shop fact these routes return is read through the `campus-customs` MCP server over
`.mcp.json` — the same path the agents use. `main.py` never opens the database. The one
exception is `/api/reset`, which copies one file over another; that is file management,
not a shop lookup.

| Route | What it does |
|---|---|
| `GET /` | Desk dashboard — a small control page so payments and purchases can actually be clicked for approval. |
| `GET /api/tickets` | Returns all three tickets with `is_open` and a `state` of open or resolved, read via `list_open_tickets(include_closed=true)`. |
| `POST /api/run` | Runs the full agent team on a random open ticket (or a named `ticket_id`), returning the disposition, desks consulted, actions taken, money moved, and token cost. |
| `GET /api/events` | Recent agent activity from the append-only audit trail: which agent spoke, what it said, which MCP tools it called, and which writes were refused. |
| `POST /api/approve` | Executes a payment or a stock purchase after a human clicks approve; the MCP safety checks still apply, so an over-amount or repeat payment is refused even when approved. |
| `GET /api/balance` | Current `checking` balance from `cash_accounts`, with total obligations and what would remain if all were paid. |
| `POST /api/reset` | Restores `data/campus_customs_new.db` from the pristine `data/campus_customs.db` for a fresh run; the audit trail is deliberately left intact. |
| `GET /api/health` | Confirms the server is up and the MCP connection is live, listing the ten tools it can see. |

Interactive API docs are at `http://localhost:8000/docs`.

### Verified behaviour

Approval does not bypass safety. Tested live against the running server:

| Request | Result |
|---|---|
| Approve $500 against the $840 invoice | **Refused** — `amount_mismatch` |
| Approve the correct $840 | Paid; balance $3,400.00 → $2,560.00 |
| Approve the same invoice again | **Refused** — `already_paid` |
| Approve a purchase of 12 tees in size S | Booked in; stock 0 → 12 |

Each refusal is written to the audit trail as a `guardrail` record, so an auditor can
count blocked writes without reading every tool result.


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
