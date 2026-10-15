# Desk Board — design decisions

The dashboard in `frontend/` (React + Vite + TypeScript) is the human side of the agent
team. This file records what I chose, and why.

The whole board answers one question — **"what still needs me?"** — because the agents
escalate rather than spend. On the recorded runs the team moved **$0.00** and handed two
decisions back to a person. The board exists to make those handoffs obvious.

---

## 1. Layout — three columns, fixed roles

```
┌──────────┬────────────────────────────┬────────────┐
│  QUEUE   │   THE WORK                 │  THE MONEY │
│          │   ticket · desks · stream  │  cash      │
│  310px   │   fluid                    │  approve   │
└──────────┴────────────────────────────┴────────────┘
```

**Why three fixed columns rather than a single scrolling feed.** The three questions a
person asks at this desk never change: *what needs doing*, *what is happening*, *can we
afford it*. Giving each a permanent home means the eye learns one map and stops
searching. A feed would force re-reading the same layout every time something changed.

**Why the queue is narrowest and the work is widest.** The queue is a list of five words
per row; the agent transcript is paragraphs. Column width follows how much there is to
read, not an even split.

**Why money sits on the right, always visible.** Cash is the constraint on every decision
the team escalates. If the balance were a tab you had to open, you would approve a
payment without seeing the $160 it leaves behind. It is on screen permanently so the
cost of a decision is visible *while* making it.

**Why each column scrolls independently.** A long transcript must not push the approve
button off screen. The columns are `overflow-y: auto` inside a fixed-height shell, so
the queue and the money stay put while the transcript grows.

Below 1180px the money column drops to a full-width row; below 820px everything stacks.
The order degrades to queue → work → money, which is also the order of importance.

---

## 2. How the agents read differently

The five agents do different jobs, so they look different. The aim is that after about
thirty seconds a reader can follow a run **without reading a single agent name**.

| Agent | Colour | Glyph | Owns |
|---|---|---|---|
| Shift manager | Yale navy `#00356b`, **solid fill** | ★ | Routes and decides |
| Inventory | Amber `#a8620a` | ▦ | Stock and shortfalls |
| Accounting | Green `#13754a` | $ | Cash, bills, margins |
| Facilities | Violet `#5b3fa8` | ⌂ | Lease, rent, landlord |
| Customer service | Teal `#0d6b78` | ✉ | What the requester is told |

**Why the boss is the odd one out.** It gets a **full-width lane**, a **solid** navy
badge, and sits above the four specialists, which are rendered as lighter tinted chips.
That is not decoration — it encodes the actual hierarchy. The boss is the only agent
that decides; the other four advise it and cannot act on their own authority. The layout
should make a reader expect that before they are told.

**Why colour and not just labels.** The amber lane means stock. Green means money. Once
that is learned, a glance at the transcript's colour rail shows the *shape* of a run —
"boss asked stock, then money, then drafted a reply" — without parsing any words.

**Two views of the same run, because they answer different questions:**

- **The roster** (five lanes) answers *who is working right now*. Lanes are `idle`
  (55% opacity), `active` (accent border, pulsing left rail), or `reported`. Idle desks
  show what they own; engaged desks show their latest line. This is the live view.
- **The transcript** answers *what was actually said*. Every step in order, keyed to its
  agent's colour, with the real question the boss asked and the real answer it got.

A delegation row is coloured by the **desk being asked**, not by the boss, and reads
`Boss → Inventory`. The thread a reader follows is the specialist's, so that is the
colour the row takes.

**Tool calls are chips, and writes look different from reads.** Reads are violet, writes
amber, refusals red and struck through. A refused write is the single most important
thing on the board — it means a guardrail fired — so it is the only element that is
simultaneously red, struck through, and labelled with its reason (`already_paid`,
`insufficient_funds`). The verbs are translated too: `delegation_result` is unreadable,
so it renders as "reported back".

---

## 3. How resolved tickets read

Closed tickets **stay in the queue** under a `CLOSED` divider, greyed (`--sunk`
background, softer text) but still clickable.

**Why not hide them.** Half the value of this board is reviewing what the agents decided.
Hiding closed work would hide exactly that. But open work must win the eye, so the
contrast between the two groups does the sorting — the bright group is the one that
needs you.

**Why the status badge is not just "closed".** The four dispositions mean genuinely
different things and are coloured accordingly:

| Status | Reads as | Colour |
|---|---|---|
| `resolved` | **Resolved** | green |
| `declined` | **Declined** | red |
| `escalated` | **Needs you** | amber |
| `blocked` | **Blocked** | grey |

`escalated` is relabelled **"Needs you"** deliberately. "Escalated" describes what the
agent did; "Needs you" describes what the human must do. The board is for the human, so
it uses the human's framing — and amber keeps it visually closer to open work than to
finished work, which is accurate, because an escalated ticket is not done.

**The summary card** appears under the ticket once a run finishes: the disposition and
money moved in a coloured bar, then the decision in plain prose, the desks consulted as
coloured chips, what was actually done, the question waiting on a human, and the drafted
customer reply. Token cost sits in small grey text at the bottom — real but not the
point. `actions_taken` lists only writes that genuinely succeeded, so the card cannot
claim credit for a refused write.

---

## 4. How cash reads

The balance is the largest number on the board, in Yale navy, tabular-figure aligned.

**Why a split meter under it.** `$3,400.00` on its own is misleading when `$3,240.00` of
it is already committed to an overdue invoice and rent. The meter splits the account
into **owed** (amber) and **free** (green), so the honest number — $160 — is a visible
proportion rather than arithmetic the reader has to do. This is the single most
important thing the money panel communicates, because it is the exact trade-off the
agents keep escalating.

**Why a thin remainder triggers a warning.** Under $500 free, an amber note appears
saying the team is expected to escalate rather than spend down to this. It explains the
agents' behaviour at the moment the reader is most likely to wonder why nothing was paid.

**Why the ledger repeats the numbers.** Balance → obligations → if-all-paid, as three
rows. The meter is for scanning; the rows are for checking. Neither alone is enough when
money is involved.

**Why approval sits directly beneath cash.** Approving a payment and seeing what it
leaves are the same decision. They share a column so the balance updates in place the
moment an approval goes through.

**Why the refusal text is shown verbatim.** When an approved payment is refused, the
panel prints the backend's own message — *"Refusing to pay $500.00 for invoice 501: the
ledger says $840.00 is owed."* Paraphrasing it would obscure which rule fired. The
standing note under the form says plainly that approval does not bypass the safety
checks, because a human clicking Approve reasonably expects it to be final, and here it
is not.

---

## 5. Smaller decisions

**Runs are asynchronous.** `POST /api/run` returns a `run_id` immediately and works in
the background; the board polls the run status and the audit trail every 1.2s. A
blocking 30-second request would have meant a spinner and no insight. Polling the trail
is what makes the desks visible *while* they work — and it reuses the audit log already
being written, rather than adding a second channel that could disagree with it.

**The live chip in the top bar** pulses only while a run is in flight, and the working
ticket's queue badge switches to "Working…", so progress is visible from any column.

**Closing a ticket by hand requires a note.** The confirm button stays disabled until
something is typed. A ticket closed without a reason is useless to whoever reads it next,
and the MCP tool refuses it anyway — the UI enforces the same rule earlier so the user
is not bounced by an error.

**Failure is explicit.** If the backend is unreachable the board replaces itself with the
exact command to start it. Mid-run model failures surface as a red "Run failed" card with
the real error. One run during testing died on a provider connection error; it was caught,
written to the audit trail, and shown as a failure rather than an empty result.

**Restraint:** no charts, no icon library, no animation beyond the two pulses that
indicate live state. Three fonts weights, one accent per agent. The data is dense enough;
decoration would compete with it.

---

## Running it

```bash
# backend, from backend/
uvicorn main:app --reload --port 8000

# board, from frontend/
npm run dev          # http://localhost:5173
```

The backend allows `http://localhost:5173` by name in its CORS list, and Vite is pinned
to that port with `strictPort: true` so it fails loudly rather than drifting to 5174 and
being silently blocked by the browser.
