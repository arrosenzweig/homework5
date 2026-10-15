"""The team's single connection to the shop database.

Every shop fact the agents use arrives through the `campus-customs` MCP server defined
in `.mcp.json`. This module is the **only** bridge: nothing in `backend/` imports
sqlite3, opens the database, or reimplements a shop lookup. If a fact is not available
through an MCP tool, the agents do not have it.

That is a deliberate constraint, not an accident of layout. A second data path would
mean two sets of rules about what may be promised and what may be spent, and the one
that bypassed MCP would bypass the safety checks built into the write tools.

This module also installs the audit hook: `process_tool_call` wraps every MCP call so
the trail records who called what, with which arguments, and what came back — including
refusals.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from fastmcp import Client
from pydantic_ai.mcp import MCPToolset

HW5_ROOT = Path(__file__).resolve().parent.parent
MCP_CONFIG = HW5_ROOT / ".mcp.json"

# Tools that change the database. Used to flag writes in the audit trail and to keep
# read-only desks read-only.
WRITE_TOOLS = {"record_payment", "adjust_stock", "resolve_ticket", "post_desk_note"}

# Least privilege: which desk may see which tools. A desk cannot call what it cannot
# see, so customer service structurally cannot move money and facilities cannot pay.
DESK_TOOLS: dict[str, set[str]] = {
    "boss": {"list_open_tickets", "get_ticket", "resolve_ticket", "post_desk_note"},
    "inventory": {
        "check_stock", "find_vendor", "adjust_stock", "get_ticket", "post_desk_note",
    },
    "accounting": {
        "get_cash_and_obligations", "get_price_and_margin", "record_payment",
        "get_ticket", "post_desk_note",
    },
    "facilities": {"get_cash_and_obligations", "get_ticket", "post_desk_note"},
    "customer_service": {
        "get_ticket", "check_stock", "get_price_and_margin", "post_desk_note",
    },
}


def load_config() -> dict:
    """Read .mcp.json — the same file any MCP client uses.

    The `args` path in that file is relative to the folder a client is launched from,
    which is the usual MCP convention. The FastAPI app runs from `backend/`, so the
    script path is resolved against the HW 5 root here before the subprocess is spawned.
    `.mcp.json` itself stays portable and unmodified.
    """
    if not MCP_CONFIG.exists():
        raise FileNotFoundError(
            f"{MCP_CONFIG} is missing. It defines the campus-customs MCP connection."
        )
    config = json.loads(MCP_CONFIG.read_text(encoding="utf-8"))
    for server in config.get("mcpServers", {}).values():
        server["args"] = [
            str(HW5_ROOT / arg)
            if arg.endswith(".py") and not Path(arg).is_absolute()
            else arg
            for arg in server.get("args", [])
        ]
    return config


def _summarise(result: Any) -> tuple[str, bool, str | None]:
    """Condense a tool result for the audit trail; surface refusals explicitly."""
    ok, refusal = True, None
    data = result
    if isinstance(data, dict):
        if data.get("ok") is False:
            ok = False
            refusal = data.get("refusal_reason")
        text = data.get("summary") or data.get("message") or json.dumps(data, default=str)
    else:
        text = str(data)
    return (text[:400], ok, refusal)


def build_toolset(desk: str, audit, deps_hint: str | None = None) -> MCPToolset:
    """Build an MCP toolset scoped to one desk, with audit logging attached.

    Args:
        desk: Which desk this toolset is for; decides which tools are visible.
        audit: An `AuditTrail` the hook writes every call to.
        deps_hint: Optional label recorded alongside each call.
    """
    allowed = DESK_TOOLS.get(desk, set())

    async def process_tool_call(ctx, call_tool, name, tool_args):
        """Audit hook: every MCP call the team makes passes through here."""
        started = time.monotonic()
        ticket_id = None
        for key in ("ticket_id", "ref_id"):
            if isinstance(tool_args, dict) and isinstance(tool_args.get(key), int):
                ticket_id = tool_args[key]
                break
        try:
            result = await call_tool(name, tool_args)
        except Exception as exc:  # noqa: BLE001 - the trail must capture failures too
            audit.tool_call(
                agent=desk, tool=name, args=dict(tool_args or {}),
                result_summary=f"EXCEPTION: {exc}", ok=False,
                duration_ms=int((time.monotonic() - started) * 1000),
                is_write=name in WRITE_TOOLS, ticket_id=ticket_id,
            )
            raise
        summary, ok, refusal = _summarise(result)
        audit.tool_call(
            agent=desk, tool=name, args=dict(tool_args or {}), result_summary=summary,
            ok=ok, refusal_reason=refusal,
            duration_ms=int((time.monotonic() - started) * 1000),
            is_write=name in WRITE_TOOLS, ticket_id=ticket_id,
        )
        if not ok:
            # A refused write is a guardrail doing its job; record it as such so an
            # auditor can count them without parsing every tool result.
            audit.guardrail(
                agent=desk, rule=f"mcp:{refusal or 'refused'}",
                detail=f"{name} refused: {summary[:200]}", ticket_id=ticket_id,
            )
        return result

    toolset = MCPToolset(
        Client(load_config()),
        id=f"campus-customs:{desk}",
        process_tool_call=process_tool_call,
    )
    if allowed:
        toolset = toolset.filtered(lambda ctx, td, _a=allowed: td.name in _a)
    return toolset
