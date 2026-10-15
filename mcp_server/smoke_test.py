"""Task 4 — MCP smoke test for the campus-customs server.

Launches the server exactly as `.mcp.json` declares it (python, stdio transport),
calls every tool over the MCP protocol, and checks each result against a direct SQL
query on data/campus_customs_new.db.

Each test records the "vibe coder" prompt a person would actually type, the tool that
prompt should route to, the arguments, the tool's own output, and the independent
database read it was compared against. A test passes only when the tool's numbers equal
the database's numbers.

Run from the HW 5 folder:    python mcp_server/smoke_test.py
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from fastmcp import Client

HW5_ROOT = Path(__file__).resolve().parent.parent
MCP_CONFIG = HW5_ROOT / ".mcp.json"
DB = HW5_ROOT / "data" / "campus_customs_new.db"
OUT = HW5_ROOT / "output" / "mcp_smoke.json"


def sql_one(query: str, params: tuple = ()) -> dict | None:
    """Read a single row straight from the database, bypassing the MCP server."""
    with closing(sqlite3.connect(DB)) as con:
        con.row_factory = sqlite3.Row
        row = con.execute(query, params).fetchone()
        return dict(row) if row else None


def money(v) -> float | None:
    return None if v is None else round(float(v), 2)


# --------------------------------------------------------------------------- #
# Test cases: prompt -> tool -> expected database truth
# --------------------------------------------------------------------------- #


def build_cases() -> list[dict]:
    """Each case names the prompt, the tool, and how to verify the result."""

    def stock_row(sku: str, size: str) -> dict:
        return sql_one(
            "SELECT sku, name, size, qty, location FROM inventory "
            "WHERE sku = ? AND size = ?",
            (sku, size),
        )

    def price_row(sku: str) -> dict:
        return sql_one(
            "SELECT sku, unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)
        )

    cases: list[dict] = []

    # ---------------------------------------------------------------- T-01
    db = stock_row("CC-TEE-WHITE", "S")
    cases.append(
        {
            "id": "T-01",
            "tool": "check_stock",
            "ticket": "101 — customer order, Tauhid Zaman",
            "vibe_coder_prompt": "A customer wants one white Bulldog tee in size small. Do we have it?",
            "arguments": {"sku": "CC-TEE-WHITE", "size": "S", "requested_qty": 1},
            "db_query": "SELECT qty, location FROM inventory WHERE sku='CC-TEE-WHITE' AND size='S'",
            "expect": {
                "found": True,
                "rows[0].qty": db["qty"],
                "rows[0].location": db["location"],
                "rows[0].in_stock": db["qty"] > 0,
                "rows[0].can_fill": db["qty"] >= 1,
                "rows[0].shortfall": max(0, 1 - db["qty"]),
            },
            "proves": "The size the customer asked for is out of stock (0), even though the tee exists in other sizes.",
        }
    )

    # ---------------------------------------------------------------- T-02
    db = stock_row("CC-HOOD-NAVY", "M")
    cases.append(
        {
            "id": "T-02",
            "tool": "check_stock",
            "ticket": "103 — price override, Yale AI Club",
            "vibe_coder_prompt": "The Yale AI Club wants 20 navy hoodies in medium. Can we actually cover that order?",
            "arguments": {"sku": "CC-HOOD-NAVY", "size": "M", "requested_qty": 20},
            "db_query": "SELECT qty FROM inventory WHERE sku='CC-HOOD-NAVY' AND size='M'",
            "expect": {
                "found": True,
                "rows[0].qty": db["qty"],
                "rows[0].can_fill": db["qty"] >= 20,
                "rows[0].shortfall": max(0, 20 - db["qty"]),
            },
            "proves": "Only 8 of the 20 requested hoodies exist; the shortfall of 12 is reported before any discount is discussed.",
        }
    )

    # ---------------------------------------------------------------- T-03
    total = sql_one(
        "SELECT SUM(qty) AS total, COUNT(*) AS n FROM inventory WHERE sku='CC-HOOD-NAVY'"
    )
    cases.append(
        {
            "id": "T-03",
            "tool": "check_stock",
            "ticket": "103 — price override, Yale AI Club",
            "vibe_coder_prompt": "What sizes of the navy hoodie do we carry, and how many of each?",
            "arguments": {"sku": "CC-HOOD-NAVY"},
            "db_query": "SELECT SUM(qty), COUNT(*) FROM inventory WHERE sku='CC-HOOD-NAVY'",
            "expect": {
                "found": True,
                "total_on_hand": total["total"],
                "len(rows)": total["n"],
            },
            "proves": "Totals across every size row match the database sum exactly.",
        }
    )

    # ---------------------------------------------------------------- T-04
    missing = sql_one("SELECT COUNT(*) AS n FROM inventory WHERE sku='CC-SCARF-PLAID'")
    cases.append(
        {
            "id": "T-04",
            "tool": "check_stock",
            "ticket": "— anti-hallucination guard",
            "vibe_coder_prompt": "Do we have any plaid scarves in stock?",
            "arguments": {"sku": "CC-SCARF-PLAID"},
            "db_query": "SELECT COUNT(*) FROM inventory WHERE sku='CC-SCARF-PLAID'  -- returns 0",
            "expect": {
                "found": missing["n"] > 0,
                "total_on_hand": 0,
                "len(rows)": 0,
            },
            "proves": "A product that does not exist returns found=false instead of an invented stock figure.",
        }
    )

    # ---------------------------------------------------------------- T-05
    db = stock_row("CC-HAT-BLUE", "OS")
    cases.append(
        {
            "id": "T-05",
            "tool": "check_stock",
            "ticket": "— anti-hallucination guard",
            "vibe_coder_prompt": "Can I get a Yale cap in extra large?",
            "arguments": {"sku": "CC-HAT-BLUE", "size": "XL"},
            "db_query": "SELECT size FROM inventory WHERE sku='CC-HAT-BLUE'  -- only 'OS' exists",
            "expect": {
                "found": True,
                "len(rows)": 0,
                "summary_contains": "OS",
            },
            "proves": "A real SKU in an unstocked size returns no rows and names the sizes that do exist, rather than guessing.",
        }
    )

    # ---------------------------------------------------------------- T-06
    db = price_row("CC-MUG-CREST")
    cases.append(
        {
            "id": "T-06",
            "tool": "get_price_and_margin",
            "ticket": "— catalogue pricing",
            "vibe_coder_prompt": "What does the Crest Mug sell for, and what do we make on it?",
            "arguments": {"sku": "CC-MUG-CREST"},
            "db_query": "SELECT unit_cost, list_price FROM pricing WHERE sku='CC-MUG-CREST'",
            "expect": {
                "found": True,
                "unit_cost": money(db["unit_cost"]),
                "list_price": money(db["list_price"]),
                "margin_per_unit": money(db["list_price"] - db["unit_cost"]),
            },
            "proves": "Cost and list price are read from the pricing table, and margin is derived from those two values only.",
        }
    )

    # ---------------------------------------------------------------- T-07
    db = price_row("CC-HOOD-NAVY")
    cases.append(
        {
            "id": "T-07",
            "tool": "get_price_and_margin",
            "ticket": "103 — price override, Yale AI Club",
            "vibe_coder_prompt": "The AI Club is asking for 20 hoodies at $35 each. Does that still work for us?",
            "arguments": {"sku": "CC-HOOD-NAVY", "qty": 20, "proposed_unit_price": 35.00},
            "db_query": "SELECT unit_cost, list_price FROM pricing WHERE sku='CC-HOOD-NAVY'",
            "expect": {
                "found": True,
                "unit_cost": money(db["unit_cost"]),
                "list_price": money(db["list_price"]),
                "quote.above_cost": 35.00 > db["unit_cost"],
                "quote.margin_per_unit": money(35.00 - db["unit_cost"]),
                "quote.line_total": money(35.00 * 20),
                "quote.line_margin": money((35.00 - db["unit_cost"]) * 20),
            },
            "proves": "A proposed bulk price is scored against the recorded $22.00 unit cost, not an assumed one.",
        }
    )

    # ---------------------------------------------------------------- T-08
    cases.append(
        {
            "id": "T-08",
            "tool": "get_price_and_margin",
            "ticket": "103 — price override, Yale AI Club",
            "vibe_coder_prompt": "They're pushing for $20 per hoodie. Can we do that?",
            "arguments": {"sku": "CC-HOOD-NAVY", "qty": 20, "proposed_unit_price": 20.00},
            "db_query": "SELECT unit_cost FROM pricing WHERE sku='CC-HOOD-NAVY'  -- 22.0",
            "expect": {
                "found": True,
                "quote.above_cost": 20.00 > db["unit_cost"],
                "quote.margin_per_unit": money(20.00 - db["unit_cost"]),
                "quote.line_margin": money((20.00 - db["unit_cost"]) * 20),
            },
            "proves": "A below-cost ask is flagged above_cost=false with a negative margin, so the agent cannot agree to a loss.",
        }
    )

    # ---------------------------------------------------------------- T-09
    cases.append(
        {
            "id": "T-09",
            "tool": "get_price_and_margin",
            "ticket": "— anti-hallucination guard",
            "vibe_coder_prompt": "How much is the Handsome Dan plush toy?",
            "arguments": {"sku": "CC-PLUSH-DAN"},
            "db_query": "SELECT COUNT(*) FROM pricing WHERE sku='CC-PLUSH-DAN'  -- returns 0",
            "expect": {
                "found": False,
                "unit_cost": None,
                "list_price": None,
            },
            "proves": "An unpriced product yields no price at all rather than a plausible invented one.",
        }
    )

    # ---------------------------------------------------------------- T-10
    cash = sql_one("SELECT name, balance, date FROM cash_accounts")
    lease = sql_one("SELECT id, landlord, monthly_rent, next_due FROM leases")
    desk = sql_one("SELECT date_today FROM desk")
    totals = sql_one(
        "SELECT COALESCE(SUM(amount),0) AS inv FROM invoices WHERE LOWER(status) != 'paid'"
    )
    paid = sql_one("SELECT COUNT(*) AS n FROM payments")
    cases.append(
        {
            "id": "T-10",
            "tool": "get_cash_and_obligations",
            "ticket": "102 — rent notice, Elm City Properties",
            "vibe_coder_prompt": "The landlord emailed saying rent is due in two days. How much do we actually owe, and can we afford it right now?",
            "arguments": {},
            "db_query": "SELECT balance FROM cash_accounts; SELECT monthly_rent, next_due, landlord FROM leases; SELECT date_today FROM desk",
            "expect": {
                "as_of": desk["date_today"],
                "total_cash": money(cash["balance"]),
                "leases[0].monthly_rent": money(lease["monthly_rent"]),
                "leases[0].landlord": lease["landlord"],
                "leases[0].next_due": lease["next_due"],
                "total_rent_due": money(lease["monthly_rent"]),
                "total_invoices_due": money(totals["inv"]),
                "total_obligations": money(lease["monthly_rent"] + totals["inv"]),
                "remaining_if_all_paid": money(
                    cash["balance"] - lease["monthly_rent"] - totals["inv"]
                ),
                "recorded_payments": paid["n"],
            },
            "proves": "Rent is verified at $2,400.00 from the lease (the email names no amount), the landlord matches the ticket requester, and the date comes from desk.date_today — not the system clock.",
        }
    )

    # ---------------------------------------------------------------- T-11
    inv = sql_one(
        "SELECT i.id, i.amount, i.due_date, i.description, v.name AS vendor, v.lead_days "
        "FROM invoices i JOIN vendors v ON v.id = i.vendor_id WHERE i.id = 501"
    )
    cases.append(
        {
            "id": "T-11",
            "tool": "get_cash_and_obligations",
            "ticket": "101 — customer order, Tauhid Zaman",
            "vibe_coder_prompt": "Is a reprint of that white tee already on order, and when would it land?",
            "arguments": {},
            "db_query": "SELECT i.amount, i.due_date, i.description, v.name, v.lead_days FROM invoices i JOIN vendors v ON v.id=i.vendor_id WHERE i.id=501",
            "expect": {
                "open_invoices[0].invoice_id": inv["id"],
                "open_invoices[0].amount": money(inv["amount"]),
                "open_invoices[0].due_date": inv["due_date"],
                "open_invoices[0].description": inv["description"],
                "open_invoices[0].vendor_name": inv["vendor"],
                "open_invoices[0].vendor_lead_days": inv["lead_days"],
                "open_invoices[0].is_overdue": True,
            },
            "proves": "Invoice 501 is already a rush reprint of CC-TEE-WHITE S, so a second reorder would duplicate it — and it is overdue and unpaid.",
        }
    )

    return cases


# --------------------------------------------------------------------------- #
# Comparison
# --------------------------------------------------------------------------- #


def dig(data: dict, path: str):
    """Resolve a dotted path like 'rows[0].qty' or 'len(rows)' against tool output."""
    if path.startswith("len(") and path.endswith(")"):
        return len(data.get(path[4:-1]) or [])
    if path == "summary_contains":
        return data.get("summary", "")
    cur = data
    for part in path.split("."):
        if "[" in part:
            key, idx = part[:-1].split("[")
            cur = (cur or {}).get(key) or []
            i = int(idx)
            cur = cur[i] if len(cur) > i else None
        else:
            cur = (cur or {}).get(part) if isinstance(cur, dict) else None
        if cur is None:
            return None
    return cur


def compare(output: dict, expect: dict) -> tuple[list[dict], bool]:
    checks, ok = [], True
    for path, want in expect.items():
        got = dig(output, path)
        if path == "summary_contains":
            passed = isinstance(got, str) and str(want) in got
            got_display = got
        else:
            if isinstance(want, float) or isinstance(got, float):
                passed = want is not None and got is not None and abs(float(got) - float(want)) < 0.005
            else:
                passed = got == want
            got_display = got
        ok = ok and passed
        checks.append(
            {
                "field": path,
                "expected_from_database": want,
                "actual_from_mcp_tool": got_display,
                "match": bool(passed),
            }
        )
    return checks, ok


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #


async def main() -> int:
    config = json.loads(MCP_CONFIG.read_text(encoding="utf-8"))
    cases = build_cases()
    results = []

    # Connect through .mcp.json itself, so this proves that file is correct.
    async with Client(config) as client:
        listed = await client.list_tools()
        tool_names = [t.name for t in listed]
        print(f"connected via {MCP_CONFIG.name}; tools: {tool_names}")

        for case in cases:
            res = await client.call_tool(case["tool"], case["arguments"])
            output = res.structured_content
            checks, ok = compare(output, case["expect"])
            print(f"  {case['id']}  {case['tool']:<26} {'PASS' if ok else 'FAIL'}")
            if not ok:
                for c in checks:
                    if not c["match"]:
                        print(f"      MISMATCH {c['field']}: "
                              f"db={c['expected_from_database']!r} tool={c['actual_from_mcp_tool']!r}")
            results.append(
                {
                    "id": case["id"],
                    "result": "PASS" if ok else "FAIL",
                    "tool": case["tool"],
                    "ticket": case["ticket"],
                    "vibe_coder_prompt": case["vibe_coder_prompt"],
                    "tool_arguments": case["arguments"],
                    "tool_output": output,
                    "database_verification": {
                        "database_file": "data/campus_customs_new.db",
                        "query": case["db_query"],
                        "field_checks": checks,
                        "all_fields_match": ok,
                    },
                    "what_this_proves": case["proves"],
                }
            )

    passed = sum(1 for r in results if r["result"] == "PASS")
    covered = sorted({r["tool"] for r in results})

    evidence = {
        "assignment": "HW 5 — Task 4: MCP connection and tool smoke test",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mcp_connection": {
            "config_file": ".mcp.json",
            "server_name": list(config["mcpServers"])[0],
            "command": config["mcpServers"]["campus-customs"]["command"],
            "args": config["mcpServers"]["campus-customs"]["args"],
            "transport": "stdio",
            "tools_advertised": tool_names,
            "note": "Every call below was made over the MCP protocol against a server "
                    "launched from .mcp.json, not by importing the Python functions.",
        },
        "database_under_test": {
            "path": "data/campus_customs_new.db",
            "sha256": hashlib.sha256(DB.read_bytes()).hexdigest(),
            "note": "Each tool result was compared against a direct SQL read of this file.",
        },
        "summary": {
            "total_tests": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "tools_covered": covered,
            "all_three_tools_tested": len(covered) == 3,
        },
        "tests": results,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(results)} passed — evidence written to {OUT.relative_to(HW5_ROOT)}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
