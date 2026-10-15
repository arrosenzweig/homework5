"""Append-only audit trail for the Campus Customs agent team.

Every run writes what the team actually did: which agent was asked what, which MCP
tool it called with which arguments, what came back, whether a write was refused, how
the loop terminated, and what it all cost in tokens. Without this an agent team is a
black box — you can read the final answer but not the path that produced it, which
makes a wrong decision impossible to diagnose and a spending spike impossible to
attribute to an agent.

## File format

`output/audit_trail.json` is **JSON Lines**: one complete JSON object per line.

That is deliberate rather than a single JSON array. An array has to be read, parsed,
extended and rewritten on every append — so the whole history is rewritten constantly,
a crash mid-write can truncate the entire file, and two writers can lose each other's
records. JSON Lines appends one line and never touches what came before, so the file is
genuinely append-only and a partial write can at worst damage its own last line.

Read it back with:

    [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]

## Guarantees

* Opened with mode `"a"` only. Nothing here truncates, rewrites, or deletes the file,
  and no other module in this assignment writes to it. Re-running the team **appends**
  to the existing history; it never wipes it.
* A logging failure never breaks a run — auditing is best-effort and swallows its own
  errors, because losing a log line is better than losing the shift.
* Arguments and results are summarised and length-capped, so the trail cannot grow into
  a second copy of the shop database.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HW5_ROOT = Path(__file__).resolve().parent.parent
AUDIT_PATH = Path(
    os.environ.get("CAMPUS_CUSTOMS_AUDIT", HW5_ROOT / "output" / "audit_trail.json")
)

_LOCK = threading.Lock()
_MAX_FIELD = 600  # characters kept from any single argument or result


def _clip(value: Any, limit: int = _MAX_FIELD) -> Any:
    """Shrink a value so the trail stays a log, not a database dump."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + f"... [+{len(value)-limit} chars]"
    if isinstance(value, dict):
        return {k: _clip(v, 200) for k, v in list(value.items())[:25]}
    if isinstance(value, (list, tuple)):
        head = [_clip(v, 200) for v in list(value)[:10]]
        if len(value) > 10:
            head.append(f"... [+{len(value)-10} more]")
        return head
    text = str(value)
    return text if len(text) <= limit else text[:limit] + "..."


class AuditTrail:
    """One run's worth of audit records, all sharing a run_id."""

    def __init__(self, run_id: str | None = None, path: Path | None = None):
        self.run_id = run_id or f"run-{uuid.uuid4().hex[:12]}"
        self.path = Path(path) if path else AUDIT_PATH
        self._seq = 0
        self._t0 = time.monotonic()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # -- core ------------------------------------------------------------- #

    def record(self, event: str, **fields: Any) -> dict:
        """Append one record. Never raises."""
        with _LOCK:
            self._seq += 1
            seq = self._seq
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "run_id": self.run_id,
            "seq": seq,
            "elapsed_ms": int((time.monotonic() - self._t0) * 1000),
            "event": event,
            **{k: _clip(v) for k, v in fields.items() if v is not None},
        }
        line = json.dumps(entry, ensure_ascii=False, default=str)
        try:
            with _LOCK, self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass  # best effort: never let logging break a shift
        return entry

    # -- typed helpers ----------------------------------------------------- #

    def run_start(self, **f: Any) -> dict:
        return self.record("run_start", **f)

    def run_end(self, **f: Any) -> dict:
        return self.record("run_end", **f)

    def ticket_start(self, ticket_id: int, **f: Any) -> dict:
        return self.record("ticket_start", ticket_id=ticket_id, **f)

    def ticket_end(self, ticket_id: int, **f: Any) -> dict:
        return self.record("ticket_end", ticket_id=ticket_id, **f)

    def delegation(self, frm: str, to: str, question: str, ticket_id: int | None = None) -> dict:
        return self.record(
            "delegation", agent=frm, delegated_to=to, question=question, ticket_id=ticket_id
        )

    def delegation_result(
        self, to: str, summary: str, ticket_id: int | None = None, **f: Any
    ) -> dict:
        return self.record(
            "delegation_result", agent=to, result_summary=summary, ticket_id=ticket_id, **f
        )

    def tool_call(
        self,
        agent: str,
        tool: str,
        args: dict,
        result_summary: str,
        ok: bool = True,
        duration_ms: int | None = None,
        is_write: bool = False,
        refusal_reason: str | None = None,
        ticket_id: int | None = None,
    ) -> dict:
        """The record that makes a write auditable: who, what, with what, and the outcome."""
        return self.record(
            "tool_call",
            agent=agent,
            tool=tool,
            is_write=is_write,
            args=args,
            result_summary=result_summary,
            ok=ok,
            refusal_reason=refusal_reason,
            duration_ms=duration_ms,
            ticket_id=ticket_id,
        )

    def usage(self, agent: str, usage_obj: Any, ticket_id: int | None = None) -> dict:
        """Token spend, so cost can be attributed to a specific agent."""
        return self.record(
            "usage",
            agent=agent,
            ticket_id=ticket_id,
            requests=getattr(usage_obj, "requests", None),
            input_tokens=getattr(usage_obj, "input_tokens", None),
            output_tokens=getattr(usage_obj, "output_tokens", None),
            total_tokens=getattr(usage_obj, "total_tokens", None),
            tool_calls=getattr(usage_obj, "tool_calls", None),
        )

    def guardrail(self, agent: str, rule: str, detail: str, ticket_id: int | None = None) -> dict:
        """A safety rule firing — a limit hit, a refusal honoured, an escalation."""
        return self.record(
            "guardrail", agent=agent, rule=rule, detail=detail, ticket_id=ticket_id
        )

    def error(self, agent: str, message: str, ticket_id: int | None = None, **f: Any) -> dict:
        return self.record("error", agent=agent, message=message, ticket_id=ticket_id, **f)


def read_trail(path: Path | None = None) -> list[dict]:
    """Load every record ever written, across all runs."""
    p = Path(path) if path else AUDIT_PATH
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # tolerate a torn final line rather than losing the file
    return out
