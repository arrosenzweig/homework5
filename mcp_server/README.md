# Campus Customs MCP Server

A [FastMCP](https://github.com/jlowin/fastmcp) server that exposes the Campus Customs
shop database to the agents in this assignment.

## What this server is for

Campus Customs is a small Yale apparel and gift shop. Its operations — stock, prices,
vendor bills, rent, and cash — live in a SQLite database. An agent asked to work the
shop's front desk needs that data to answer anything useful, and it must not make any
of it up.

This server is the **single, shared data layer** for every agent in the assignment.
Rather than giving each agent its own database connection and its own chance to
misread the schema, all of them connect to this one server and call the same audited
tools. That gives three things:

1. **One source of truth.** Every figure an agent quotes — a quantity, a price, a
   balance, a due date — came from a `SELECT` against the shop database.
2. **No hallucination, by construction.** The tools have no defaults and no fallbacks.
   A product that isn't on file comes back as `found = false` with an explicit
   explanation, never as a plausible-looking guess. Even "today" is read from the
   database (`desk.date_today` = `2026-08-31`) rather than the system clock, so an
   agent can't misjudge a deadline by comparing 2026 due dates against the real date.
3. **Typed results.** Every tool returns a Pydantic model, so agents receive named
   fields they can quote directly instead of prose they have to re-parse.

## Which database it uses

```
data/campus_customs_new.db     <- this server reads this file (the working copy)
data/campus_customs.db         <- the pristine data pack; never touched
```

The server reads **`data/campus_customs_new.db`**, the working copy created in Task 2.
The original data pack stays untouched so any run can be reset and compared against the
starting state.

The path resolves relative to the `HW 5` folder, so the server works from any working
directory. Override it if needed:

```bash
export CAMPUS_CUSTOMS_DB=/path/to/another.db
```

The three tools in this version are **read-only** — they only issue `SELECT`
statements. They point at the working copy so that later tasks, which do write, operate
on the same file.

## The ten tools

Six read the shop; four change it. Every agent in the assignment reaches the database
through these and nothing else.

| # | Tool | Kind | Tables |
|---|---|---|---|
| 1 | `check_stock` | read | `inventory` |
| 2 | `get_price_and_margin` | read | `pricing` |
| 3 | `get_cash_and_obligations` | read | `cash_accounts`, `invoices`, `vendors`, `leases`, `payments`, `desk` |
| 4 | `list_open_tickets` | read | `tickets`, `desk` |
| 5 | `get_ticket` | read | `tickets` + linked `inventory`, `pricing`, `invoices`, `vendors`, `leases` |
| 6 | `find_vendor` | read | `vendors`, `invoices` |
| 7 | `record_payment` | **write** | `payments`, `cash_accounts`, `invoices` |
| 8 | `adjust_stock` | **write** | `inventory` |
| 9 | `resolve_ticket` | **write** | `tickets` |
| 10 | `post_desk_note` | **write** | `desk` |

---

## Read tools

### 1. `check_stock(sku, size=None, requested_qty=None)`

Units on hand for a product, by size.

Reads **`inventory`**. Stock is keyed by `(sku, size)`, so this is the only way to tell
whether the specific size a customer asked for actually exists. Pass `requested_qty` and
each row reports `can_fill` and `shortfall`.

```
check_stock("CC-TEE-WHITE", "S", requested_qty=1)
-> "Classic Bulldog Tee (CC-TEE-WHITE) size S is OUT OF STOCK: 0 on hand in Aisle B."
```

### 2. `get_price_and_margin(sku, qty=1, proposed_unit_price=None)`

Cost, list price, and whether a proposed discount clears cost.

Reads **`pricing`**. `unit_cost` is the floor — a price at or below it sells at a loss.
Pass `proposed_unit_price` to have a specific ask evaluated, and `qty` to get line
totals at the right volume.

```
get_price_and_margin("CC-HOOD-NAVY", qty=20, proposed_unit_price=35.00)
-> unit cost $22.00, list $58.00; at $35.00 (39.7% off) margin is $13.00/unit,
   ABOVE cost. For 20 units: $700.00 revenue, $260.00 margin.
```

### 3. `get_cash_and_obligations()`

The full money picture: what's in the bank against everything owed.

Reads **`cash_accounts`**, **`invoices`**, **`vendors`**, **`leases`**, **`payments`**,
and **`desk`**. Returns balances, every unpaid invoice (joined to its vendor for
`lead_days`, flagged overdue against `desk.date_today`), rent **as recorded on the
lease**, the totals, and what's left if it's all paid. Takes no arguments — it's a
snapshot of the whole position.

```
get_cash_and_obligations()
-> "As of 2026-08-31: $3400.00 cash across 1 account(s). 1 unpaid invoice(s)
    totalling $840.00, 1 already overdue. Rent on file totals $2400.00.
    Paying everything leaves $160.00. No payments have been recorded yet."
```

### 4. `list_open_tickets(ticket_type=None)`

The work queue — the first call of any shift.

Reads **`tickets`** for rows still `open`, and **`desk`** to age each one. Filter by
`"customer_order"`, `"rent_notice"`, or `"price_override"`, or omit for everything.

### 5. `get_ticket(ticket_id)`

One ticket plus every record it links to, in a single call.

Reads **`tickets`**, then follows the links: `sku`/`size` into **`inventory`** and
**`pricing`**, `invoice_id` into **`invoices`** (joined to **`vendors`**), `lease_id`
into **`leases`**. This is the main token saving in the system — one call where four
would otherwise be needed, which is why every agent's first move on a ticket is this.

### 6. `find_vendor(specialty=None)`

Suppliers, their turnaround, and what they are already owed.

Reads **`vendors`**, plus **`invoices`** to count each one's unpaid bills. Substring
match on specialty (`"apparel"`, `"courier"`). The unpaid totals matter: a vendor owed
money may not rush a job.

---

## Write tools

These four change the database. Their safety rules are enforced **in code** — an agent
cannot argue past them, because the tool returns `ok: false` and commits nothing. Always
check `ok` before reporting something as done.

### 7. `record_payment(kind, ref_id, amount, account, approved_by, memo=None)`

Pay a vendor invoice or rent. The only way money leaves the shop.

Writes **`payments`** (one row), **`cash_accounts`** (balance decremented), and
**`invoices`** (status → paid) in a single transaction. Reads **`leases`** and
**`desk`** to validate.

Refused, with nothing written, when:

| Refusal | Meaning |
|---|---|
| `insufficient_funds` | The balance would go negative. No overdraft, ever. |
| `already_paid` | The invoice is settled, or a payment row already exists for it. |
| `amount_mismatch` | The amount does not equal what the ledger says is owed. |
| `no_approver` | `approved_by` was empty. Every payment names a human. |
| `ref_not_found` / `account_not_found` | The invoice, lease, or account does not exist. |

### 8. `adjust_stock(sku, size, delta, reason)`

Commit units out (negative delta) or book a delivery in (positive).

Writes **`inventory`**. Refused with `would_go_negative` if the change would drive a
count below zero — the shop cannot hold negative stock, and a shortfall must be
reported rather than papered over. A `reason` is required.

### 9. `resolve_ticket(ticket_id, status, resolution_note)`

Close a ticket as `resolved`, `declined`, `escalated`, or `blocked`.

Writes **`tickets`**. The note is **appended** to any existing notes, not substituted
for them. A note is required, so every closed ticket carries a reason an auditor can
read.

### 10. `post_desk_note(author, note)`

Append a line to the shared desk notes — the team's common workspace.

Writes **`desk`**. Every agent reads and writes the same `desk.notes` field, so this is
how one desk leaves a finding for another and how a shift hands off to the next. Lines
are timestamped with the dataset's date and attributed to their author. **Appends
only**; nothing already written is overwritten.

---

See [`../output/harness.md`](../output/harness.md) for the full mapping of each tool to
the open tickets it unlocks, which agent holds which tools, and the safety guardrails.

## Running it

Install the dependency:

```bash
pip install fastmcp
```

Start the server (stdio transport):

```bash
python mcp_server/server.py
```

## Connecting a client (`.mcp.json`)

The connection is registered for this assignment in [`../.mcp.json`](../.mcp.json) at the
`HW 5` root:

```json
{
  "mcpServers": {
    "campus-customs": {
      "command": "python",
      "args": ["mcp_server/server.py"]
    }
  }
}
```

Scoping it to `HW 5` rather than a global config means the server is available to this
assignment only. The `args` path is **relative to the folder the client is launched
from**, so start the client from `HW 5`. The database path does not share that
constraint — `db.py` resolves it relative to its own file location, so the server finds
`data/campus_customs_new.db` from any working directory.

A client already running when this file was added needs a restart to pick it up.

### Verifying the connection

`smoke_test.py` connects *through* `.mcp.json` — it reads that file and launches the
server from it over stdio, so a passing run proves the config itself is correct, not just
that the Python functions work:

```bash
python mcp_server/smoke_test.py
```

It calls all three tools, compares every returned figure against a direct SQL read of the
database, and writes the evidence to [`../output/mcp_smoke.json`](../output/mcp_smoke.json).

## Layout

| File | Purpose |
|---|---|
| `server.py` | The FastMCP app and the three tool definitions. |
| `db.py` | Connection handling, path resolution, and `today()` — the single place the dataset's date is read. |
| `models.py` | Pydantic return types for every tool, so results are typed and self-describing. |
| `README.md` | This file. |

## Notes for later tasks

- `payments` is empty and is the intended **append-only** write target.
- `desk.notes` is `NULL` and is available as agent scratch memory.
- Writes should go to `campus_customs_new.db` only. Reset by re-copying from
  `campus_customs.db`.
