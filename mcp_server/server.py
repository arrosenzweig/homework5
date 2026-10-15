"""Campus Customs MCP server.

A FastMCP server exposing the shop's operations database to every agent in this
assignment. The three tools below are the agent's only route to shop data.

Hard rule, enforced by construction: **every number these tools return comes from a
SELECT against the database.** There are no defaults, no fallbacks, and no estimates.
A SKU that is not on file returns `found = False` with an explicit summary rather than
a plausible-looking guess, and "today" is read from `desk.date_today` rather than the
system clock.

Run it with:    python mcp_server/server.py
"""

from __future__ import annotations

import sys
from contextlib import closing
from datetime import date, timedelta

from fastmcp import FastMCP

from db import connect, db_path, money, today
from models import (
    AccountBalance,
    CashPosition,
    LeaseObligation,
    OpenInvoice,
    PriceQuote,
    PricingReport,
    StockReport,
    StockRow,
)

mcp = FastMCP(
    name="campus-customs",
    instructions=(
        "Operations data for the Campus Customs shop (Yale apparel and gifts). "
        "Use check_stock before promising any item to a customer, get_price_and_margin "
        "before quoting or discounting any price, and get_cash_and_obligations before "
        "approving any payment. Every figure these tools return is read from the shop "
        "database. If a tool reports found = false, the record does not exist — say so "
        "rather than estimating."
    ),
)


# --------------------------------------------------------------------------- #
# Tool 1 — check_stock
# --------------------------------------------------------------------------- #


@mcp.tool
def check_stock(
    sku: str,
    size: str | None = None,
    requested_qty: int | None = None,
) -> StockReport:
    """Look up units on hand for a product, by size, from the inventory table.

    Call this before promising, reserving, or selling anything. Stock is tracked per
    (sku, size), so a product can be well stocked overall and still unavailable in the
    size a customer asked for.

    Args:
        sku: Product code, e.g. "CC-TEE-WHITE". Case-insensitive.
        size: Restrict to one size ("S", "M", "L", "XL", or "OS" for one-size goods).
            Omit to see every size of the product.
        requested_qty: Units the customer wants. When given, each row reports whether
            on-hand stock covers it and by how much it falls short.

    Returns:
        StockReport. `found = False` means the SKU is not in inventory at all; a row
        with `qty = 0` means the size exists but is out of stock. Neither is a reason
        to estimate — report exactly what came back.
    """
    sku_key = sku.strip().upper()
    size_key = size.strip().upper() if size else None

    with closing(connect()) as con:
        if size_key:
            cur = con.execute(
                "SELECT sku, name, size, qty, location FROM inventory "
                "WHERE UPPER(sku) = ? AND UPPER(size) = ?",
                (sku_key, size_key),
            )
        else:
            cur = con.execute(
                "SELECT sku, name, size, qty, location FROM inventory "
                "WHERE UPPER(sku) = ? ORDER BY rowid",
                (sku_key,),
            )
        records = cur.fetchall()

        # Distinguish "no such SKU" from "that size is not stocked".
        sku_exists = bool(
            con.execute(
                "SELECT 1 FROM inventory WHERE UPPER(sku) = ? LIMIT 1", (sku_key,)
            ).fetchone()
        )

    if not records:
        if sku_exists and size_key:
            stocked = ", ".join(_sizes_for(sku_key))
            summary = (
                f"{sku_key} is in inventory but size {size_key} is not stocked. "
                f"Sizes on file: {stocked}."
            )
        else:
            summary = f"{sku_key} is not in the inventory table. No stock data exists for it."
        return StockReport(
            sku=sku_key,
            found=sku_exists,
            requested_size=size_key,
            requested_qty=requested_qty,
            rows=[],
            total_on_hand=0,
            summary=summary,
        )

    rows: list[StockRow] = []
    for rec in records:
        can_fill = None
        shortfall = None
        if requested_qty is not None:
            can_fill = rec["qty"] >= requested_qty
            shortfall = max(0, requested_qty - rec["qty"])
        rows.append(
            StockRow(
                sku=rec["sku"],
                name=rec["name"],
                size=rec["size"],
                qty=rec["qty"],
                location=rec["location"],
                in_stock=rec["qty"] > 0,
                can_fill=can_fill,
                shortfall=shortfall,
            )
        )

    total = sum(r.qty for r in rows)
    name = rows[0].name

    if size_key:
        row = rows[0]
        if row.qty == 0:
            summary = f"{name} ({sku_key}) size {row.size} is OUT OF STOCK: 0 on hand in {row.location}."
        elif requested_qty is not None and not row.can_fill:
            summary = (
                f"{name} ({sku_key}) size {row.size} has {row.qty} on hand in {row.location}, "
                f"short {row.shortfall} of the {requested_qty} requested."
            )
        else:
            summary = f"{name} ({sku_key}) size {row.size} has {row.qty} on hand in {row.location}."
    else:
        breakdown = ", ".join(f"{r.size}={r.qty}" for r in rows)
        summary = f"{name} ({sku_key}) has {total} units on hand across {len(rows)} size(s): {breakdown}."

    return StockReport(
        sku=sku_key,
        found=True,
        requested_size=size_key,
        requested_qty=requested_qty,
        rows=rows,
        total_on_hand=total,
        summary=summary,
    )


def _sizes_for(sku_key: str) -> list[str]:
    """Sizes actually stocked for a SKU, used only to make a miss explicit."""
    with closing(connect()) as con:
        return [
            r["size"]
            for r in con.execute(
                "SELECT size FROM inventory WHERE UPPER(sku) = ? ORDER BY rowid",
                (sku_key,),
            )
        ]


# --------------------------------------------------------------------------- #
# Tool 2 — get_price_and_margin
# --------------------------------------------------------------------------- #


@mcp.tool
def get_price_and_margin(
    sku: str,
    qty: int = 1,
    proposed_unit_price: float | None = None,
) -> PricingReport:
    """Look up cost and list price for a product and check a discount against them.

    Call this before quoting any price and before agreeing to any discount. `unit_cost`
    is the floor: a price at or below it sells at a loss. Pricing is held per SKU, so
    all sizes of a product share one price — do not invent size-based pricing.

    Args:
        sku: Product code, e.g. "CC-HOOD-NAVY". Case-insensitive.
        qty: Units being quoted, so line totals are costed at the right volume.
        proposed_unit_price: A per-unit price someone has asked for. When given, the
            report shows the discount off list, the resulting margin, and whether the
            price clears cost.

    Returns:
        PricingReport. `found = False` means the SKU has no pricing row, so no price
        may be quoted for it at all.
    """
    sku_key = sku.strip().upper()
    if qty < 1:
        qty = 1

    with closing(connect()) as con:
        rec = con.execute(
            "SELECT sku, unit_cost, list_price FROM pricing WHERE UPPER(sku) = ?",
            (sku_key,),
        ).fetchone()

    if rec is None:
        return PricingReport(
            sku=sku_key,
            found=False,
            qty=qty,
            summary=(
                f"{sku_key} has no row in the pricing table. There is no cost or list "
                "price on file, so no price can be quoted for it."
            ),
        )

    unit_cost = money(rec["unit_cost"])
    list_price = money(rec["list_price"])
    margin = money(list_price - unit_cost)
    margin_pct = money(margin / list_price * 100) if list_price else 0.0
    list_line_total = money(list_price * qty)

    quote = None
    if proposed_unit_price is not None:
        proposed = money(proposed_unit_price)
        q_margin = money(proposed - unit_cost)
        quote = PriceQuote(
            proposed_unit_price=proposed,
            discount_off_list=money(list_price - proposed),
            discount_pct=money((list_price - proposed) / list_price * 100) if list_price else 0.0,
            margin_per_unit=q_margin,
            margin_pct=money(q_margin / proposed * 100) if proposed else 0.0,
            above_cost=proposed > unit_cost,
            line_total=money(proposed * qty),
            line_margin=money(q_margin * qty),
        )

    summary = (
        f"{sku_key}: unit cost ${unit_cost:.2f}, list price ${list_price:.2f}, "
        f"margin ${margin:.2f} ({margin_pct:.1f}%) per unit."
    )
    if quote is not None:
        verdict = "ABOVE cost" if quote.above_cost else "AT OR BELOW cost - this loses money"
        summary += (
            f" At ${quote.proposed_unit_price:.2f} ({quote.discount_pct:.1f}% off list) "
            f"the margin is ${quote.margin_per_unit:.2f}/unit, {verdict}. "
            f"For {qty} unit(s): ${quote.line_total:.2f} revenue, "
            f"${quote.line_margin:.2f} margin."
        )

    return PricingReport(
        sku=sku_key,
        found=True,
        unit_cost=unit_cost,
        list_price=list_price,
        margin_per_unit=margin,
        margin_pct=margin_pct,
        qty=qty,
        list_line_total=list_line_total,
        quote=quote,
        summary=summary,
    )


# --------------------------------------------------------------------------- #
# Tool 3 — get_cash_and_obligations
# --------------------------------------------------------------------------- #


@mcp.tool
def get_cash_and_obligations() -> CashPosition:
    """Report cash on hand against every unpaid invoice and rent obligation.

    Call this before approving, scheduling, or promising any payment. It verifies what
    is owed against the ledger rather than against whatever a notice or email claims,
    ranks obligations by their real due dates, and reports what is left if everything
    is paid.

    Due-date arithmetic is measured against `desk.date_today`, the dataset's current
    date, not the real clock.

    Returns:
        CashPosition: balances, open invoices (with the vendor's lead time and an
        overdue flag), lease obligations with the rent amount **as recorded on the
        lease**, the totals, and how much cash remains if all of it is paid.
    """
    with closing(connect()) as con:
        now = today(con)

        accounts = [
            AccountBalance(
                name=r["name"], balance=money(r["balance"]), as_of=r["date"]
            )
            for r in con.execute(
                "SELECT name, balance, date FROM cash_accounts ORDER BY name"
            )
        ]

        invoices: list[OpenInvoice] = []
        for r in con.execute(
            "SELECT i.id, i.vendor_id, i.amount, i.due_date, i.status, i.description, "
            "       v.name AS vendor_name, v.specialty, v.lead_days "
            "FROM invoices i JOIN vendors v ON v.id = i.vendor_id "
            "WHERE LOWER(i.status) != 'paid' "
            "ORDER BY i.due_date"
        ):
            due = _as_date(r["due_date"])
            days = (due - now).days if due else 0
            eta = (due + timedelta(days=r["lead_days"])).isoformat() if due else None
            invoices.append(
                OpenInvoice(
                    invoice_id=r["id"],
                    vendor_id=r["vendor_id"],
                    vendor_name=r["vendor_name"],
                    vendor_specialty=r["specialty"],
                    vendor_lead_days=r["lead_days"],
                    amount=money(r["amount"]),
                    due_date=r["due_date"],
                    status=r["status"],
                    description=r["description"],
                    days_until_due=days,
                    is_overdue=days < 0,
                    expected_delivery_date=eta,
                )
            )

        # A lease has no `status` column the way an invoice does, and `next_due` is not
        # rolled forward when rent is paid. So the ledger is the authority on whether
        # this period's rent is settled: a payments row of kind 'rent' against the
        # lease means it is. Without this the tool keeps reporting rent as owed after
        # it has been paid, and every "remaining if all paid" figure is wrong.
        leases: list[LeaseObligation] = []
        for r in con.execute(
            "SELECT l.id, l.space_name, l.landlord, l.monthly_rent, l.next_due, l.notes, "
            "       (SELECT COUNT(*) FROM payments p "
            "        WHERE LOWER(p.kind) = 'rent' AND p.ref_id = l.id) AS paid_count "
            "FROM leases l ORDER BY l.next_due"
        ):
            if r["paid_count"]:
                continue  # rent for this period is already settled
            due = _as_date(r["next_due"])
            days = (due - now).days if due else 0
            leases.append(
                LeaseObligation(
                    lease_id=r["id"],
                    space_name=r["space_name"],
                    landlord=r["landlord"],
                    monthly_rent=money(r["monthly_rent"]),
                    next_due=r["next_due"],
                    days_until_due=days,
                    is_overdue=days < 0,
                    notes=r["notes"],
                )
            )

        paid_count = con.execute("SELECT COUNT(*) AS n FROM payments").fetchone()["n"]

    total_cash = money(sum(a.balance for a in accounts))
    total_invoices = money(sum(i.amount for i in invoices))
    total_rent = money(sum(l.monthly_rent for l in leases))
    total_obligations = money(total_invoices + total_rent)
    remaining = money(total_cash - total_obligations)

    overdue = [i for i in invoices if i.is_overdue]
    parts = [
        f"As of {now.isoformat()}: ${total_cash:.2f} cash across {len(accounts)} account(s).",
        f"{len(invoices)} unpaid invoice(s) totalling ${total_invoices:.2f}"
        + (f", {len(overdue)} already overdue." if overdue else "."),
        f"Rent on file totals ${total_rent:.2f}.",
        f"Paying everything leaves ${remaining:.2f}.",
    ]
    if paid_count == 0:
        parts.append("No payments have been recorded yet.")

    return CashPosition(
        as_of=now.isoformat(),
        accounts=accounts,
        total_cash=total_cash,
        open_invoices=invoices,
        leases=leases,
        total_invoices_due=total_invoices,
        total_rent_due=total_rent,
        total_obligations=total_obligations,
        remaining_if_all_paid=remaining,
        can_cover_all=remaining >= 0,
        recorded_payments=paid_count,
        summary=" ".join(parts),
    )


def _as_date(text: str | None) -> date | None:
    """Parse an ISO date stored as text; return None rather than guessing."""
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


# Ticket, vendor, and action tools live in tools_tickets.py and attach to this
# same app, so agents see one server with one tool list.
import tools_tickets  # noqa: E402

tools_tickets.register(mcp)


if __name__ == "__main__":
    print(f"campus-customs MCP server reading {db_path()}", file=sys.stderr)
    mcp.run()
