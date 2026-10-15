# AI Prompts Log — HW 5

A record of the prompts given to Claude (Claude Code, Opus 5) while completing this
assignment, organized by task. Prompts are recorded verbatim, in the order they were
asked.

All data for this assignment is sourced from `data/` and all outputs are written inside
the `HW 5` folder.

---

## Task 1 — AI prompt log and data setup

1. > We are going to source all our data and put all our outputs in the hw 5 folder. first things first. lets make our classic ai_prompt.md file. like always, insert all my prompts there with subsections for each number task i am on. this is task 1. also unzip the data file in the folder

**Produced:** `AI_prompts.md`, `data/campus_customs.db` (unzipped from `data (1).zip`)

---

## Task 2 — Database harness

2. > open the data/campus_customs.db and process the tables. copy this file to data/campus_customs_new.db which will be used as the working copy to update later. we are also going to create our classic output/harness.md where we will have each table and field and why the table is important to agent this is task 2 btw

**Produced:** `data/campus_customs_new.db` (working copy, made with SQLite's backup API and
verified identical), `output/harness.md` (all 9 tables, every field, and why each matters to
the agent)

---

## Task 3 — MCP server

3. > in mcp/server wrtie an mcp server in it using FastMCP. every agent in this assignment will be using tools in this server. for now lets start by creating 3 tools in it with clear names. never hallucinate only pull from database. in harness file list these mcp tools including the tables it reads, tickets it helps unlock, and why that tool is the right choice for that ticket. dont be vague!! specifically tie the tool to the ticket! create an mcp_server/README.md that explains what mcp server is for, which database file it uses, and the 3 tools it has. this is task 3 btw

**Produced:** `mcp_server/server.py` (FastMCP server `campus-customs` with `check_stock`,
`get_price_and_margin`, `get_cash_and_obligations`), `mcp_server/db.py` (connection and
`desk.date_today` as the only clock), `mcp_server/models.py` (typed Pydantic returns),
`mcp_server/README.md`, and an **MCP Tools** section in `output/harness.md` tying each tool
to the specific ticket it unlocks

---

## Task 4 — MCP connection and smoke test

4. > add mcp to this specific assignment. save connection in .mcp.json at project root. test each mcp tool we created. save evidence in output/mcp_smoke.json including: vibe coder prompt, tool name, and tool output that matches data/campus_customs_new.db. this is task 4

**Produced:** `.mcp.json` (the `campus-customs` connection, scoped to `HW 5`),
`mcp_server/smoke_test.py` (connects through `.mcp.json` over stdio and checks every tool
result against direct SQL), `output/mcp_smoke.json` (11 tests, all passing, each with the
vibe-coder prompt, tool name, arguments, full tool output, and the database comparison),
plus a connection/verification section in `mcp_server/README.md`

---

## Task 5 — Pydantic AI agent team

5. > for task 5. we are going to make a PydancticAI agent team inlcuidng boss, inventory, accounting, facitliites, and customer service. each agent should have prompts, models and looping to delegate work for a collaborating workspace. agent prompts need to go in backend/prompts/ with a different file per agent. data types go in backend/models.py. agent files go in backend/. add more tools the agent needs in mcp server to wokr on open tickets. the facts on the shop come from mcp server over data/campus_customs_new.db. DO NOT create second shop tools layer that bypasses mcp. agents must append to output/audit_trail.json while running looping with enough recorded for later audit. append do not wipe after each run. in harness, list each agent and tool like before plus used tables by tool. add a safety guardrails section to protect customers and their money and saves tokens. the mcp_server/README.md must match my new tool list

**Produced:** seven new MCP tools in `mcp_server/tools_tickets.py` (`list_open_tickets`,
`get_ticket`, `find_vendor`, `record_payment`, `adjust_stock`, `resolve_ticket`,
`post_desk_note`); `backend/prompts/` with `_shared.md`, `boss.md`, `inventory.md`,
`accounting.md`, `facilities.md`, `customer_service.md`; `backend/models.py`,
`backend/agents.py` (five agents with delegation tools and shared token budget),
`backend/mcp_client.py` (the single MCP bridge, with the audit hook and per-desk tool
filtering), `backend/audit.py`, `backend/run_team.py`; `output/audit_trail.json`
(append-only JSON Lines) and `output/shift_report.json`; new **full MCP tool list**,
**agent team**, **safety guardrails**, and **audit trail** sections in
`output/harness.md`; rewritten tool list in `mcp_server/README.md`

---

## Task 6 — Expected-behaviour ticket page

6. > for task 6, create output/desk_tickets.html where its a page that can be double tapped to show a tab per ticket. add empty cash and reflections tabs. for each ticket tab created an expected section that is the only section filled saying what we expect team to do on each open ticket (write who boss should call first and why, all expected agent delegations--dont let it be general call out agent names, mcp tools expected to be used in run). each ticket will also have an actual section that should be left blank for now. only fill expected section but create everything i described.

**Produced:** `output/desk_tickets.html` — five tabs (one per ticket plus empty Cash and
Reflections). Each ticket tab has a filled **Expected** section naming the boss's first
call with the reason, every delegation in order with the exact question asked, the
specific MCP tools each desk should call and what each should return, the tools expected
*not* to be called, and the expected disposition — plus a blank **Actual** section

---

## Task 7 — FastAPI backend

7. > for task 7, in backend/main.py use FastAPI and routes to: return 3 tickets plus whether they are open or resolved, run agent team on a random ticket id, recent agent events like what each said and tools they used, approve payment and purchase after click of approval, current checking balance from cash_accounts, and reset database to original values in fresh run. start server in backend/ with uvicorn main:app --reload --port 8000. this will turn on this backend at http://localhost:8000. list each route in one line in harness file (url + what it does)

**Produced:** `backend/main.py` (FastAPI app with `/api/tickets`, `/api/run`,
`/api/events`, `/api/approve`, `/api/balance`, `/api/reset`, plus `/api/health`),
`backend/static/desk.html` (control page so approvals can be clicked),
`.claude/launch.json`; `include_closed` added to `list_open_tickets` so resolved tickets
can be listed; `mcp_client.load_config()` now resolves the MCP script path against the
HW 5 root so the server connects when uvicorn runs from `backend/`; a **FastAPI routes**
section in `output/harness.md`

---

## Task 8 — React dashboard

8. > for task 8 lets build frontend/ for frontend dashboard using React, Vite, and TypeScript. the board must include: all tickets, allow you to pick a ticket and send agent team to work on it, show each agent and what they are doing for ticket, mark ticket as resolved, show short summary of what agent did for ticket, allow manual approval of purchase when asked, show checking balance. IT IS KEY for the dashboard to be creative, organized, clean, innovative, beauitful!! front end talked to backend at http://localhost:8000. allow vite page origin (http://localhost:5173) so browser can call routes. start board with npm run dev. write output/design.md with my dahboard design prefrences and why (layout, how agents read differntly, how resolved tickets and cash show)

**Produced:** `frontend/` (React + Vite + TypeScript) with `src/lib/api.ts`,
`src/lib/agents.ts` (per-agent colour, glyph and role identity), and components
`TicketQueue`, `TicketDetail`, `AgentRoster`, `AgentStream`, `CashPanel`, `ApprovePanel`;
CORS for `http://localhost:5173` plus asynchronous runs (`POST /api/run` returns a
`run_id`), `GET /api/run/{run_id}` and `POST /api/tickets/{id}/resolve` added to
`backend/main.py`; `output/design.md` covering the three-column layout, how each agent
reads differently, and how resolved tickets and cash are presented

---

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
