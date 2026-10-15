# Campus Customs — Multi-Agent Operations

A back-office agent team for Campus Customs, a small Yale apparel and gift shop on
Chapel Street. Five Pydantic AI agents work the shop's ticket queue, reaching every
shop fact through a single MCP server, behind a FastAPI backend and a React dashboard.

The shop opens the shift with **$3,400.00**, three open tickets, one overdue vendor
invoice, and rent due in two days. Working that shift correctly is the whole problem.

---

## What is here

| Piece | Where | What it does |
|---|---|---|
| **MCP server** | `mcp_server/` | Ten tools over the shop database. The only route to shop data. |
| **Agent team** | `backend/agents.py`, `backend/prompts/` | Boss plus inventory, accounting, facilities and customer service. |
| **Backend** | `backend/main.py` | FastAPI: tickets, runs, events, approvals, balance, reset. |
| **Dashboard** | `frontend/` | React + Vite + TypeScript operations board. |
| **Deliverables** | `output/` | Harness, smoke tests, ticket pages, design notes, audit trail. |

Two design rules hold the whole thing together:

1. **Every shop fact comes from the MCP server.** Nothing in `backend/` opens the
   database. There is no second tools layer that could bypass the write guardrails.
2. **The dangerous rules live in code, not prompts.** No overdraft, no double payment,
   no wrong amount, no negative stock — the MCP write tools refuse these outright, so
   neither an agent nor a human approval can talk past them.

---

## Setup

### 1. Install

```bash
pip install -r requirements.txt
```

```bash
npm install --prefix frontend
```

Python 3.11+ and Node 18+.

### 2. Add your key

```bash
cp .env.example .env
```

Then edit `.env` and set `PORTKEY_API_KEY`. The real `.env` is git-ignored and is not in
this repository.

### 3. Copy the original database to the working copy

Two database files ship under `data/`:

- `campus_customs.db` — the **pristine data pack**. Never written to.
- `campus_customs_new.db` — the **working copy**. Everything writes here.

A clean run starts by replacing the working copy with the original:

```bash
python -c "import sqlite3; s=sqlite3.connect('data/campus_customs.db'); d=sqlite3.connect('data/campus_customs_new.db'); s.backup(d); d.close(); print('working copy reset')"
```

Both files are committed, so this works straight after a clone. A plain `cp` works too,
but the `backup()` call above is transaction-safe if anything else is mid-write.

---

## Running it

Three processes. The MCP server is started **for** you by the backend, so in practice
you run two.

### Start the MCP server

The backend and the agent team launch it automatically over stdio, using the command in
`.mcp.json`. To run it by hand — to inspect it, or to point another MCP client at it:

```bash
python mcp_server/server.py
```

To check it independently, the smoke test connects *through* `.mcp.json` and verifies
every tool result against a direct SQL read:

```bash
python mcp_server/smoke_test.py
```

That writes `output/mcp_smoke.json`. Eleven tests, all passing.

### Start the FastAPI backend

**From the `backend/` folder:**

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Serves on **http://localhost:8000**, with interactive docs at `/docs` and a plain
control page at `/`. Check it is healthy and connected to MCP:

```bash
curl http://localhost:8000/api/health
```

### Start the React board

**From the project root**, in a second terminal:

```bash
npm run dev --prefix frontend
```

Serves on **http://localhost:5173**. The port is pinned with `strictPort: true` because
the backend's CORS allowlist names `http://localhost:5173` specifically — if Vite drifted
to another port the browser would silently block every call.

---

## Reset the database before a full three-ticket run

The agents write to the database: they close tickets, and a human approval moves real
money. Before a fresh end-to-end run, put the working copy back to its opening state.

**From the dashboard:** click **Reset day** in the top bar.

**From the API:**

```bash
curl -X POST http://localhost:8000/api/reset
```

**From the command line** (no server needed):

```bash
python -c "import sqlite3; s=sqlite3.connect('data/campus_customs.db'); d=sqlite3.connect('data/campus_customs_new.db'); s.backup(d); d.close(); print('reset')"
```

A reset restores the balance to **$3,400.00**, returns all three tickets to `open`, and
empties `payments`.

**It deliberately does not touch `output/audit_trail.json`.** That file is append-only
JSON Lines and holds the history of every run ever made, across resets. That is the point
of keeping it outside the database.

### Run the whole shift

With the database reset, work all three open tickets:

```bash
python backend/run_team.py
```

Or one ticket:

```bash
python backend/run_team.py --ticket 101
```

Or read-only, with every write tool removed from every desk:

```bash
python backend/run_team.py --dry-run
```

Each run appends to `output/audit_trail.json` and writes `output/shift_report.json`.

**Expect all three tickets to come back `escalated` with $0.00 moved.** That is correct
behaviour, not a failure: paying the $840.00 overdue invoice and the $2,400.00 rent would
leave the shop on $160.00, and the team is built to hand that decision to a human rather
than take it. Approve the payments from the dashboard, or with `POST /api/approve`, and
the tickets then close as `resolved`.

---

## Project layout

```
hw5/
├── AI_prompts.md              every prompt given to Claude, by task
├── requirements.txt
├── .env.example               template; the real .env is git-ignored
├── .gitignore
├── .mcp.json                  the campus-customs MCP connection
├── README.md
├── data/
│   ├── campus_customs.db      pristine data pack — never written to
│   └── campus_customs_new.db  working copy — everything writes here
├── mcp_server/
│   ├── server.py              FastMCP app; the read tools
│   ├── tools_tickets.py       ticket, vendor and write tools
│   ├── db.py                  the one connection, and the only clock
│   ├── models.py              typed returns for every tool
│   ├── smoke_test.py          verifies tools against direct SQL
│   └── README.md
├── frontend/                  React + Vite + TypeScript dashboard
├── backend/
│   ├── main.py                FastAPI routes
│   ├── models.py              agent data types
│   ├── agents.py              the five agents and delegation
│   ├── mcp_client.py          the single MCP bridge + audit hook
│   ├── audit.py               append-only trail
│   ├── run_team.py            shift loop
│   └── prompts/
│       ├── _shared.md         rules every agent follows
│       ├── boss.md
│       ├── inventory.md
│       ├── accounting.md
│       ├── facilities.md
│       └── customer_service.md
├── scripts/                   one-off generators for the output pages
└── output/
    ├── harness.md             tables, tools, agents, routes, safety
    ├── mcp_smoke.json         11 tool tests vs direct SQL
    ├── desk_tickets.html      Expected / Actual / Cash / Reflections tabs
    ├── design.md              dashboard design decisions
    ├── resolved_tickets.json  per-ticket outcome and agent contributions
    ├── resolved_board.html    board screenshots per resolved ticket
    ├── audit_trail.json       append-only JSON Lines, never wiped
    ├── shift_report.json      last shift summary
    └── github_url.txt
```

---

## The three tickets

Each hides something that punishes a careless agent.

| # | Ticket | The trap |
|---|---|---|
| **101** | Tauhid Zaman wants 1 × white tee, size S | The tee has **10 units** across M/L/XL — but **0** in S. And invoice 501 is *already* a rush reprint of that exact SKU, so reordering would duplicate $840. |
| **102** | Elm City Properties: "rent due in 2 days" | The email names **no amount**. The $2,400.00 comes from `leases.monthly_rent`, never from the notice. |
| **103** | Yale AI Club wants 20 hoodies, size M | Only **8** exist. It looks like a pricing question; it is a supply question. Any discount floors at the $22.00 unit cost. |

The recorded shift: all three traps caught, **$0.00** moved by the agents, closing
balance **$160.00** after a human approved $3,240.00 of payments. The full reconciliation
is in the Cash tab of `output/desk_tickets.html`.

---

## Safety

Refused by the MCP write tools, regardless of who calls them:

| Refusal | Means |
|---|---|
| `insufficient_funds` | The payment would overdraw the account. |
| `already_paid` | The invoice is settled, or a payment row already exists. |
| `amount_mismatch` | The amount does not equal what the ledger says is owed. |
| `no_approver` | `approved_by` was empty. No payment is anonymous. |
| `would_go_negative` | The stock change would drive a count below zero. |

Enforced by structure: each desk only sees the tools it needs, so customer service cannot
move money, and facilities verifies rent without being able to pay it. Enforced by budget:
per-ticket and per-shift token ceilings shared across all desks. Every tool call and every
refusal is written to the audit trail.

A human clicking **Approve** does not bypass any of this — an approved payment of the
wrong amount is still refused.

---

## Troubleshooting

**`PORTKEY_API_KEY is not set`** — copy `.env.example` to `.env` and add your key.

**Backend returns 500 on every route** — the MCP subprocess could not start. Check
`python mcp_server/server.py` runs on its own, and that `data/campus_customs_new.db`
exists.

**The board shows "Cannot reach the backend"** — the backend is not running, or it is not
on port 8000.

**The board loads but every call fails** — Vite is not on 5173. The CORS allowlist names
that port exactly.

**A run ends `ModelAPIError: Connection error`** — a transient gateway failure. It is
caught, written to the audit trail, and shown as a failed run. Re-run that ticket.
