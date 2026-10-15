"""FastAPI backend for the Campus Customs desk.

Run it from the `backend/` folder:

    uvicorn main:app --reload --port 8000

then open http://localhost:8000

Every shop fact these routes return is read through the `campus-customs` MCP server —
the same server, over the same `.mcp.json`, that the agents use. This module does not
open the database, and there is no second shop-tools layer here. The one exception is
`POST /api/reset`, which copies one file over another; that is file management, not a
shop lookup, and it is deliberately the only place a database path is touched directly.
"""

from __future__ import annotations

import json
import random
import sqlite3
import sys
from pathlib import Path
from typing import Any

import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastmcp import Client
from pydantic import BaseModel, Field

HW5_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agents import TICKET_LIMITS, ShopTeam  # noqa: E402
from audit import AuditTrail, read_trail  # noqa: E402
from mcp_client import load_config  # noqa: E402
from models import TeamDeps  # noqa: E402
from run_team import ticket_brief  # noqa: E402

PRISTINE_DB = HW5_ROOT / "data" / "campus_customs.db"
WORKING_DB = HW5_ROOT / "data" / "campus_customs_new.db"
AUDIT_FILE = HW5_ROOT / "output" / "audit_trail.json"

app = FastAPI(
    title="Campus Customs desk",
    description="Agent-team back office. All shop data arrives over MCP.",
    version="1.0.0",
)

# The Vite dev server runs on a different origin, so the browser needs explicit
# permission before it may call these routes.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-flight and finished agent runs, so the dashboard can start a run, watch the desks
# work, and collect the result — rather than holding a request open for 30 seconds.
RUNS: dict[str, dict] = {}


async def mcp_call(tool: str, args: dict | None = None) -> Any:
    """Call one MCP tool and return its structured result."""
    async with Client(load_config()) as client:
        res = await client.call_tool(tool, args or {})
        return res.structured_content


# --------------------------------------------------------------------------- #
# Request bodies
# --------------------------------------------------------------------------- #


class RunRequest(BaseModel):
    ticket_id: int | None = Field(
        default=None, description="Omit to pick a random open ticket."
    )
    approver: str = "Alexandria Rosenzweig"
    wait: bool = Field(
        default=False,
        description="True holds the request until the run finishes. False returns a "
                    "run_id straight away so the caller can watch progress.",
    )


class ResolveRequest(BaseModel):
    status: str = Field(default="resolved", description="resolved/declined/escalated/blocked.")
    note: str = Field(description="Why. Recorded on the ticket for later audit.")
    resolved_by: str = "Alexandria Rosenzweig"


class ApprovalRequest(BaseModel):
    """A human clicking Approve on something the team escalated."""

    action: str = Field(description='"payment" to settle a bill, "purchase" to book stock in.')
    approved_by: str = Field(description="Who is approving. Required — no payment is anonymous.")
    # payment
    kind: str | None = Field(default=None, description='"invoice" or "rent".')
    ref_id: int | None = Field(default=None, description="invoices.id or leases.id.")
    amount: float | None = None
    account: str = "checking"
    memo: str | None = None
    # purchase (booking restocked units in)
    sku: str | None = None
    size: str | None = None
    qty: int | None = Field(default=None, description="Units received. Positive.")
    reason: str | None = None


# --------------------------------------------------------------------------- #
# 1. Tickets
# --------------------------------------------------------------------------- #


@app.get("/api/tickets", summary="All tickets and whether each is open or resolved")
async def get_tickets() -> dict:
    """Return every ticket with its current status."""
    data = await mcp_call("list_open_tickets", {"include_closed": True})
    tickets = []
    for t in data.get("tickets", []):
        status = str(t.get("status", "")).lower()
        tickets.append(
            {
                "ticket_id": t["ticket_id"],
                "type": t["type"],
                "requester": t["requester"],
                "subject": t["subject"],
                "status": status,
                "is_open": status == "open",
                "state": "open" if status == "open" else "resolved",
                "sku": t.get("sku"),
                "size": t.get("size"),
                "qty": t.get("qty"),
                "notes": t.get("notes"),
            }
        )
    return {
        "as_of": data.get("as_of"),
        "count": len(tickets),
        "open_count": sum(1 for t in tickets if t["is_open"]),
        "resolved_count": sum(1 for t in tickets if not t["is_open"]),
        "tickets": tickets,
        "source": "campus-customs MCP · list_open_tickets",
    }


# --------------------------------------------------------------------------- #
# 2. Run the agent team
# --------------------------------------------------------------------------- #


async def _work_ticket(run_key: str, ticket: dict, approver: str) -> dict:
    """Run the full team on one ticket and record the outcome."""
    audit = AuditTrail(run_id=run_key)
    audit.run_start(approver=approver, mode="api", ticket_id=ticket["ticket_id"])
    team = ShopTeam(audit)
    deps = TeamDeps(approver=approver, audit_run_id=audit.run_id)
    team.begin_ticket(ticket["ticket_id"])
    audit.ticket_start(
        ticket["ticket_id"], type=ticket["type"], requester=ticket["requester"]
    )

    try:
        result = await team.boss.run(
            ticket_brief(ticket), deps=deps, usage_limits=TICKET_LIMITS
        )
    except Exception as exc:  # noqa: BLE001
        audit.error(agent="boss", ticket_id=ticket["ticket_id"], message=str(exc))
        audit.run_end(stop_reason="error")
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}

    res = result.output
    usage = result.usage
    audit.usage(agent="boss", usage_obj=usage, ticket_id=ticket["ticket_id"])
    audit.ticket_end(
        ticket["ticket_id"],
        disposition=res.disposition.value,
        decision=res.decision,
        actions_taken=res.actions_taken,
        money_moved=res.money_moved,
        needs_human=res.needs_human,
    )
    audit.run_end(stop_reason="completed", tickets_handled=1)

    return {
        "status": "done",
        "ticket_id": res.ticket_id,
        "ticket_subject": ticket["subject"],
        "disposition": res.disposition.value,
        "decision": res.decision,
        "specialists_consulted": [s.value for s in res.specialists_consulted],
        "actions_taken": res.actions_taken,
        "customer_message": res.customer_message,
        "money_moved": res.money_moved,
        "needs_human": res.needs_human,
        "human_question": res.human_question,
        "tokens": usage.total_tokens,
        "model_requests": usage.requests,
    }


async def _run_in_background(run_key: str, ticket: dict, approver: str) -> None:
    RUNS[run_key].update(await _work_ticket(run_key, ticket, approver))
    RUNS[run_key]["finished_at"] = datetime.now(timezone.utc).isoformat()


@app.post("/api/run", summary="Run the agent team on a random (or named) ticket")
async def run_team(req: RunRequest, background: BackgroundTasks) -> dict:
    """Dispatch the team to a ticket — at random unless one is named.

    By default this returns a `run_id` immediately and works the ticket in the
    background, so a dashboard can watch the desks report in through `/api/events`
    instead of waiting on a single long request. Pass `wait: true` for the blocking
    behaviour.
    """
    if req.ticket_id is not None:
        detail = await mcp_call("get_ticket", {"ticket_id": req.ticket_id})
        if not detail.get("found"):
            raise HTTPException(404, f"No ticket {req.ticket_id}.")
        ticket = detail["ticket"]
        picked_randomly = False
    else:
        queue = await mcp_call("list_open_tickets", {})
        open_tickets = queue.get("tickets", [])
        if not open_tickets:
            return {
                "ran": False,
                "reason": "No open tickets. Reset the database to run again.",
                "open_tickets": 0,
            }
        ticket = random.choice(open_tickets)
        picked_randomly = True

    run_key = f"run-{uuid.uuid4().hex[:12]}"
    RUNS[run_key] = {
        "run_id": run_key,
        "status": "running",
        "ticket_id": ticket["ticket_id"],
        "ticket_subject": ticket["subject"],
        "picked_randomly": picked_randomly,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    if req.wait:
        RUNS[run_key].update(await _work_ticket(run_key, ticket, req.approver))
        RUNS[run_key]["finished_at"] = datetime.now(timezone.utc).isoformat()
        return {"ran": True, **RUNS[run_key]}

    background.add_task(_run_in_background, run_key, ticket, req.approver)
    return {"ran": True, **RUNS[run_key]}


@app.get("/api/run/{run_id}", summary="Status and result of an agent run")
async def run_status(run_id: str) -> dict:
    """Poll a run started by POST /api/run."""
    run = RUNS.get(run_id)
    if run is None:
        raise HTTPException(404, f"No run {run_id}.")
    return run


@app.post("/api/tickets/{ticket_id}/resolve", summary="Mark a ticket resolved by hand")
async def resolve_ticket(ticket_id: int, req: ResolveRequest) -> dict:
    """Close a ticket manually, without running the team."""
    note = req.note.strip()
    if not note:
        raise HTTPException(400, "A note is required so the decision can be audited.")

    audit = AuditTrail()
    audit.record(
        "manual_resolution", ticket_id=ticket_id, status=req.status,
        note=note, resolved_by=req.resolved_by,
    )
    result = await mcp_call(
        "resolve_ticket",
        {
            "ticket_id": ticket_id,
            "status": req.status,
            "resolution_note": f"{note} (closed by {req.resolved_by})",
        },
    )
    if not result.get("ok"):
        raise HTTPException(400, result.get("message", "The ticket could not be closed."))
    return {
        "ticket_id": ticket_id,
        "resolved": True,
        "status": req.status,
        "message": result.get("message"),
        "changes": result.get("changes", {}),
    }


# --------------------------------------------------------------------------- #
# 3. Recent agent events
# --------------------------------------------------------------------------- #


@app.get("/api/events", summary="Recent agent activity: what each said and which tools it used")
async def get_events(limit: int = 60, run_id: str | None = None) -> dict:
    """Replay the tail of the audit trail as a readable activity feed."""
    records = read_trail(AUDIT_FILE)
    if run_id:
        records = [r for r in records if r.get("run_id") == run_id]
    tail = records[-limit:]

    events = []
    for r in tail:
        kind = r.get("event")
        item = {
            "ts": r.get("ts"),
            "run_id": r.get("run_id"),
            "seq": r.get("seq"),
            "event": kind,
            "agent": r.get("agent"),
            "ticket_id": r.get("ticket_id"),
        }
        if kind == "tool_call":
            item |= {
                "tool": r.get("tool"),
                "is_write": r.get("is_write", False),
                "args": r.get("args"),
                "said": r.get("result_summary"),
                "ok": r.get("ok"),
                "refusal_reason": r.get("refusal_reason"),
                "duration_ms": r.get("duration_ms"),
            }
        elif kind == "delegation":
            item |= {"delegated_to": r.get("delegated_to"), "said": r.get("question")}
        elif kind == "delegation_result":
            item |= {
                "said": r.get("result_summary"),
                "recommendation": r.get("recommendation"),
                "facts_used": r.get("facts_used"),
                "actions_taken": r.get("actions_taken"),
                "confidence": r.get("confidence"),
            }
        elif kind == "ticket_end":
            item |= {"said": r.get("decision"), "disposition": r.get("disposition"),
                     "money_moved": r.get("money_moved")}
        elif kind == "guardrail":
            item |= {"said": r.get("detail"), "rule": r.get("rule")}
        elif kind == "usage":
            item |= {"said": f"{r.get('total_tokens')} tokens in {r.get('requests')} request(s)"}
        elif kind in ("run_start", "run_end"):
            item |= {"said": r.get("stop_reason") or "started"}
        elif kind == "error":
            item |= {"said": r.get("message")}
        events.append(item)

    tools_used = [e["tool"] for e in events if e.get("tool")]
    return {
        "total_records_in_trail": len(records),
        "returned": len(events),
        "runs_in_trail": sorted({r.get("run_id") for r in records if r.get("run_id")}),
        "tools_used": sorted(set(tools_used)),
        "events": events,
        "source": "output/audit_trail.json (append-only)",
    }


# --------------------------------------------------------------------------- #
# 4. Approve a payment or purchase
# --------------------------------------------------------------------------- #


@app.post("/api/approve", summary="Approve a payment or a stock purchase after a human click")
async def approve(req: ApprovalRequest) -> dict:
    """Carry out what the team escalated, now that a human has approved it.

    The MCP write tools still apply every safety rule — this route cannot overdraw the
    account, pay twice, or pay the wrong amount, approval or not.
    """
    if not req.approved_by.strip():
        raise HTTPException(400, "approved_by is required; no approval is anonymous.")

    audit = AuditTrail()
    action = req.action.strip().lower()

    if action == "payment":
        if req.kind is None or req.ref_id is None or req.amount is None:
            raise HTTPException(400, "payment needs kind, ref_id and amount.")
        audit.record(
            "human_approval", action="payment", approved_by=req.approved_by,
            kind=req.kind, ref_id=req.ref_id, amount=req.amount,
        )
        result = await mcp_call(
            "record_payment",
            {
                "kind": req.kind, "ref_id": req.ref_id, "amount": req.amount,
                "account": req.account, "approved_by": req.approved_by,
                "memo": req.memo or "Approved from the desk dashboard",
            },
        )
    elif action == "purchase":
        if not req.sku or not req.size or not req.qty:
            raise HTTPException(400, "purchase needs sku, size and qty.")
        if req.qty <= 0:
            raise HTTPException(400, "qty must be positive — a purchase books stock in.")
        audit.record(
            "human_approval", action="purchase", approved_by=req.approved_by,
            sku=req.sku, size=req.size, qty=req.qty,
        )
        result = await mcp_call(
            "adjust_stock",
            {
                "sku": req.sku, "size": req.size, "delta": req.qty,
                "reason": req.reason or f"Purchase approved by {req.approved_by}",
            },
        )
    else:
        raise HTTPException(400, 'action must be "payment" or "purchase".')

    ok = bool(result.get("ok"))
    audit.record(
        "human_approval_result", action=action, ok=ok,
        refusal_reason=result.get("refusal_reason"), message=result.get("message"),
    )
    if not ok:
        audit.guardrail(
            agent="api", rule=f"mcp:{result.get('refusal_reason')}",
            detail=f"Approved {action} still refused: {result.get('message')}",
        )

    return {
        "approved_by": req.approved_by,
        "action": action,
        "executed": ok,
        "refused_reason": result.get("refusal_reason"),
        "message": result.get("message"),
        "changes": result.get("changes", {}),
        "balance_after": result.get("balance_after"),
        "note": (
            "Approval does not bypass the MCP safety checks; a refusal here means the "
            "write was rejected on its merits."
        ),
    }


# --------------------------------------------------------------------------- #
# 5. Checking balance
# --------------------------------------------------------------------------- #


@app.get("/api/balance", summary="Current checking balance from cash_accounts")
async def balance() -> dict:
    """Return the checking balance, with the obligations drawing on it."""
    data = await mcp_call("get_cash_and_obligations", {})
    accounts = data.get("accounts", [])
    checking = next(
        (a for a in accounts if str(a.get("name", "")).lower() == "checking"),
        accounts[0] if accounts else None,
    )
    if checking is None:
        raise HTTPException(500, "No cash account found in the database.")
    return {
        "account": checking["name"],
        "balance": checking["balance"],
        "as_of": checking.get("as_of") or data.get("as_of"),
        "total_obligations": data.get("total_obligations"),
        "remaining_if_all_paid": data.get("remaining_if_all_paid"),
        "can_cover_all": data.get("can_cover_all"),
        "payments_recorded": data.get("recorded_payments"),
        "source": "campus-customs MCP · get_cash_and_obligations · cash_accounts",
    }


# --------------------------------------------------------------------------- #
# 6. Reset
# --------------------------------------------------------------------------- #


@app.post("/api/reset", summary="Reset the working database to its original values")
async def reset() -> dict:
    """Restore `campus_customs_new.db` from the pristine data pack for a fresh run.

    The audit trail is **not** touched. It is append-only by design, so the history of
    previous runs survives a reset — that is the point of keeping it outside the
    database.
    """
    if not PRISTINE_DB.exists():
        raise HTTPException(500, f"Pristine database missing at {PRISTINE_DB}.")

    before = await mcp_call("get_cash_and_obligations", {})
    src = sqlite3.connect(PRISTINE_DB)
    dst = sqlite3.connect(WORKING_DB)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    after = await mcp_call("list_open_tickets", {"include_closed": True})
    audit = AuditTrail()
    audit.record(
        "database_reset",
        restored_from="data/campus_customs.db",
        restored_to="data/campus_customs_new.db",
        balance_before=before.get("total_cash"),
        tickets_after=len(after.get("tickets", [])),
        audit_trail_preserved=True,
    )

    cash = await mcp_call("get_cash_and_obligations", {})
    return {
        "reset": True,
        "restored_from": "data/campus_customs.db",
        "restored_to": "data/campus_customs_new.db",
        "balance_now": cash.get("total_cash"),
        "open_tickets_now": sum(
            1 for t in after.get("tickets", []) if str(t.get("status")).lower() == "open"
        ),
        "payments_now": cash.get("recorded_payments"),
        "audit_trail": "preserved — append-only, never wiped by a reset",
    }


# --------------------------------------------------------------------------- #
# Control page
# --------------------------------------------------------------------------- #


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard() -> str:
    """A small control page so approvals can actually be clicked."""
    return (Path(__file__).resolve().parent / "static" / "desk.html").read_text(
        encoding="utf-8"
    )


@app.get("/api/health", summary="Server and MCP connectivity check")
async def health() -> dict:
    async with Client(load_config()) as client:
        tools = [t.name for t in await client.list_tools()]
    return {"ok": True, "mcp_server": "campus-customs", "tools": tools,
            "database": "data/campus_customs_new.db"}
