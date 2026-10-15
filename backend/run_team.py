"""Run one shift of the Campus Customs agent team.

The loop:

    1. read the open ticket queue over MCP
    2. for each ticket, run the boss (which delegates to the desks it needs)
    3. record every step to output/audit_trail.json
    4. stop on the ticket cap, the shift token budget, or an empty queue

Run from the HW 5 folder:

    python backend/run_team.py                 # work every open ticket
    python backend/run_team.py --ticket 101    # one ticket only
    python backend/run_team.py --dry-run       # read-only: no writes are made
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from fastmcp import Client
from pydantic_ai.usage import RunUsage

HW5_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agents import TICKET_LIMITS, ShopTeam  # noqa: E402
from audit import AuditTrail  # noqa: E402
from mcp_client import WRITE_TOOLS, load_config  # noqa: E402
from models import Disposition, ShiftReport, TeamDeps  # noqa: E402

# Shift-wide ceilings. The per-ticket caps live in agents.TICKET_LIMITS.
MAX_TICKETS_PER_SHIFT = 10
SHIFT_TOKEN_BUDGET = 600_000


async def read_queue(ticket_id: int | None) -> list[dict]:
    """Read the work queue over MCP — the same path the agents use."""
    async with Client(load_config()) as client:
        if ticket_id is not None:
            res = await client.call_tool("get_ticket", {"ticket_id": ticket_id})
            detail = res.structured_content
            if not detail.get("found"):
                return []
            return [detail["ticket"]]
        res = await client.call_tool("list_open_tickets", {})
        return res.structured_content.get("tickets", [])


def ticket_brief(t: dict) -> str:
    """The instruction handed to the boss for one ticket."""
    bits = [
        f"Work ticket #{t['ticket_id']}.",
        f"Type: {t['type']}. From: {t['requester']}. Subject: {t['subject']}.",
    ]
    if t.get("notes"):
        bits.append(f'Their words: "{t["notes"]}"')
    if t.get("sku"):
        bits.append(
            f"Concerns {t['sku']}"
            + (f" size {t['size']}" if t.get("size") else "")
            + (f", quantity {t['qty']}" if t.get("qty") else "")
            + "."
        )
    if t.get("invoice_id"):
        bits.append(f"Linked to invoice {t['invoice_id']}.")
    if t.get("lease_id"):
        bits.append(f"Linked to lease {t['lease_id']}.")
    bits.append(
        "Start with get_ticket to pull its linked records, delegate to the desks that "
        "own part of this, then decide and close it."
    )
    return " ".join(bits)


async def main() -> int:
    ap = argparse.ArgumentParser(description="Run one Campus Customs shift.")
    ap.add_argument("--ticket", type=int, help="Work a single ticket id.")
    ap.add_argument("--approver", default="Alexandria Rosenzweig",
                    help="Human whose name goes on any payment.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Read-only: the team may look but not write.")
    ap.add_argument("--max-tickets", type=int, default=MAX_TICKETS_PER_SHIFT)
    args = ap.parse_args()

    audit = AuditTrail()
    audit.run_start(
        approver=args.approver,
        dry_run=args.dry_run,
        mode="single-ticket" if args.ticket else "full-queue",
        limits={
            "requests_per_ticket": TICKET_LIMITS.request_limit,
            "tool_calls_per_ticket": TICKET_LIMITS.tool_calls_limit,
            "tokens_per_ticket": TICKET_LIMITS.total_tokens_limit,
            "shift_token_budget": SHIFT_TOKEN_BUDGET,
            "max_tickets": args.max_tickets,
        },
    )
    print(f"run_id: {audit.run_id}")

    if args.dry_run:
        # Strip write tools from every desk for this run only.
        import mcp_client

        for desk, tools in mcp_client.DESK_TOOLS.items():
            mcp_client.DESK_TOOLS[desk] = tools - WRITE_TOOLS
        audit.guardrail(agent="shift", rule="dry_run",
                        detail="Write tools removed from every desk for this run.")

    queue = await read_queue(args.ticket)
    if not queue:
        audit.run_end(stop_reason="empty_queue", tickets_seen=0)
        print("No open tickets.")
        return 0

    shift_date = queue[0].get("created_at", "")[:10]
    team = ShopTeam(audit)
    deps = TeamDeps(approver=args.approver, audit_run_id=audit.run_id)

    resolutions, escalations, notes = [], [], []
    shift_usage = RunUsage()
    stop_reason = "completed"

    print(f"{len(queue)} open ticket(s)\n")
    for index, ticket in enumerate(queue):
        tid = ticket["ticket_id"]

        if index >= args.max_tickets:
            stop_reason = "ticket_cap_reached"
            audit.guardrail(agent="shift", rule="max_tickets",
                            detail=f"Stopped after {index} tickets.")
            break
        if shift_usage.total_tokens and shift_usage.total_tokens > SHIFT_TOKEN_BUDGET:
            stop_reason = "shift_token_budget_reached"
            audit.guardrail(agent="shift", rule="shift_token_budget",
                            detail=f"Spent {shift_usage.total_tokens} tokens; stopping.")
            break

        audit.ticket_start(tid, type=ticket["type"], requester=ticket["requester"],
                           subject=ticket["subject"])
        print(f"--- ticket #{tid} ({ticket['type']}) ---")
        team.begin_ticket(tid)

        try:
            result = await team.boss.run(
                ticket_brief(ticket), deps=deps, usage_limits=TICKET_LIMITS
            )
        except Exception as exc:  # noqa: BLE001
            kind = type(exc).__name__
            audit.error(agent="boss", ticket_id=tid, message=f"{kind}: {exc}")
            notes.append(f"Ticket {tid} failed: {kind}")
            print(f"    ERROR {kind}: {exc}\n")
            if "UsageLimit" in kind:
                stop_reason = "limit_reached"
            continue

        res = result.output
        resolutions.append(res)
        usage = result.usage
        shift_usage.incr(usage)

        audit.usage(agent="boss", usage_obj=usage, ticket_id=tid)
        audit.ticket_end(
            tid,
            disposition=res.disposition.value,
            decision=res.decision,
            specialists_consulted=[s.value for s in res.specialists_consulted],
            actions_taken=res.actions_taken,
            money_moved=res.money_moved,
            needs_human=res.needs_human,
        )

        if res.needs_human and res.human_question:
            escalations.append(f"#{tid}: {res.human_question}")

        print(f"    {res.disposition.value.upper()}: {res.decision}")
        if res.specialists_consulted:
            print(f"    desks: {', '.join(s.value for s in res.specialists_consulted)}")
        for action in res.actions_taken:
            print(f"    did: {action}")
        if res.needs_human:
            print(f"    NEEDS HUMAN: {res.human_question}")
        print(f"    tokens: {usage.total_tokens} in {usage.requests} request(s)\n")

    report = ShiftReport(
        run_id=audit.run_id,
        shift_date=shift_date,
        approver=args.approver,
        tickets_seen=len(queue),
        tickets_handled=len(resolutions),
        resolutions=resolutions,
        total_money_moved=round(sum(r.money_moved for r in resolutions), 2),
        escalations=escalations,
        stop_reason=stop_reason,
        total_requests=shift_usage.requests,
        total_input_tokens=shift_usage.input_tokens,
        total_output_tokens=shift_usage.output_tokens,
        notes=notes,
    )
    audit.run_end(
        stop_reason=stop_reason,
        tickets_seen=report.tickets_seen,
        tickets_handled=report.tickets_handled,
        total_money_moved=report.total_money_moved,
        escalations=escalations,
        total_requests=report.total_requests,
        total_input_tokens=report.total_input_tokens,
        total_output_tokens=report.total_output_tokens,
    )

    out = HW5_ROOT / "output" / "shift_report.json"
    out.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    print("=" * 60)
    print(f"{report.tickets_handled}/{report.tickets_seen} tickets handled "
          f"({stop_reason}); ${report.total_money_moved:.2f} moved; "
          f"{report.total_input_tokens + report.total_output_tokens} tokens")
    for esc in escalations:
        print(f"  escalated -> {esc}")
    print(f"audit: output/audit_trail.json   report: output/shift_report.json")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
