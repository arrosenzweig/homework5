"""Ticket, vendor, and action tools for the campus-customs MCP server.

Split from server.py to keep each file readable; `server.py` imports `register()` and
attaches every tool here to the same FastMCP app, so agents still see one server.

The write tools at the bottom are the only way anything in this assignment changes the
database. Their safety rules are enforced **in code**, not merely requested in a prompt:
an agent cannot overdraw the account, pay a bill twice, pay the wrong amount, or drive
stock negative, because each of those paths returns `ok = False` and commits nothing.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import timedelta

from db import connect, money, today
from models import (
    ActionResult,
    PaymentResult,
    PricingReport,
    StockRow,
    TicketDetail,
    TicketQueue,
    TicketSummary,
    VendorInfo,
    VendorList,
)

VALID_TICKET_STATUS = {"open", "resolved", "declined", "escalated", "blocked"}
VALID_PAYMENT_KINDS = {"invoice", "rent"}


def _ticket_summary(row: sqlite3.Row, now) -> TicketSummary:
    created = row["created_at"][:10]
    try:
        from datetime import date

        age = (now - date.fromisoformat(created)).days
    except ValueError:
        age = 0
    return TicketSummary(
        ticket_id=row["id"],
        type=row["type"],
        requester=row["requester"],
        subject=row["subject"],
        status=row["status"],
        sku=row["sku"],
        size=row["size"],
        qty=row["qty"],
        lease_id=row["lease_id"],
        invoice_id=row["invoice_id"],
        notes=row["notes"],
        created_at=row["created_at"],
        age_days=age,
    )


def register(mcp) -> None:
    """Attach every ticket/vendor/action tool to the FastMCP app."""

    # ------------------------------------------------------------------ #
    # 4. list_open_tickets
    # ------------------------------------------------------------------ #

    @mcp.tool
    def list_open_tickets(
        ticket_type: str | None = None, include_closed: bool = False
    ) -> TicketQueue:
        """List the shop's tickets — by default, only the unresolved ones.

        This is the starting point for a shift: it says what needs doing. Each ticket
        carries its own type, which decides who should handle it and what procedure
        applies.

        Args:
            ticket_type: Optionally narrow to one type: "customer_order",
                "rent_notice", or "price_override". Omit for every type.
            include_closed: Set true to include tickets already resolved, declined,
                escalated, or blocked — useful for reviewing a finished shift. Each
                ticket's own `status` says which it is.

        Returns:
            TicketQueue. An empty list genuinely means no matching work — do not invent
            tickets to fill it.
        """
        with closing(connect()) as con:
            now = today(con)
            where, params = [], []
            if not include_closed:
                where.append("LOWER(status) = 'open'")
            if ticket_type:
                where.append("LOWER(type) = ?")
                params.append(ticket_type.strip().lower())
            clause = f"WHERE {' AND '.join(where)}" if where else ""
            cur = con.execute(
                f"SELECT * FROM tickets {clause} ORDER BY created_at", tuple(params)
            )
            tickets = [_ticket_summary(r, now) for r in cur]

        scope = "ticket(s)" if include_closed else "open ticket(s)"
        if not tickets:
            msg = f"No {scope}" + (f" of type {ticket_type}." if ticket_type else ".")
        else:
            parts = ", ".join(
                f"#{t.ticket_id} {t.type} ({t.status})" for t in tickets
            )
            msg = f"{len(tickets)} {scope} as of {today_str(now)}: {parts}."

        return TicketQueue(
            as_of=today_str(now), count=len(tickets), tickets=tickets, summary=msg
        )

    # ------------------------------------------------------------------ #
    # 5. get_ticket
    # ------------------------------------------------------------------ #

    @mcp.tool
    def get_ticket(ticket_id: int) -> TicketDetail:
        """Fetch one ticket together with every record it links to.

        Resolves the ticket's SKU against inventory and pricing, its invoice_id against
        invoices (with the vendor), and its lease_id against leases — in a single call,
        so one ticket costs one round trip instead of four.

        Args:
            ticket_id: The ticket's id, e.g. 101.

        Returns:
            TicketDetail. `found = False` means no such ticket exists.
        """
        with closing(connect()) as con:
            now = today(con)
            row = con.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            if row is None:
                return TicketDetail(
                    found=False,
                    summary=f"No ticket with id {ticket_id} exists in the tickets table.",
                )

            ticket = _ticket_summary(row, now)
            stock: list[StockRow] = []
            pricing: PricingReport | None = None
            invoice = None
            lease = None

            if ticket.sku:
                if ticket.size:
                    cur = con.execute(
                        "SELECT * FROM inventory WHERE sku = ? AND size = ?",
                        (ticket.sku, ticket.size),
                    )
                else:
                    cur = con.execute(
                        "SELECT * FROM inventory WHERE sku = ? ORDER BY rowid", (ticket.sku,)
                    )
                for r in cur:
                    can_fill = None if ticket.qty is None else r["qty"] >= ticket.qty
                    short = None if ticket.qty is None else max(0, ticket.qty - r["qty"])
                    stock.append(
                        StockRow(
                            sku=r["sku"], name=r["name"], size=r["size"], qty=r["qty"],
                            location=r["location"], in_stock=r["qty"] > 0,
                            can_fill=can_fill, shortfall=short,
                        )
                    )
                p = con.execute(
                    "SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (ticket.sku,)
                ).fetchone()
                if p:
                    cost, lst = money(p["unit_cost"]), money(p["list_price"])
                    pricing = PricingReport(
                        sku=ticket.sku, found=True, unit_cost=cost, list_price=lst,
                        margin_per_unit=money(lst - cost),
                        margin_pct=money((lst - cost) / lst * 100) if lst else 0.0,
                        qty=ticket.qty or 1,
                        list_line_total=money(lst * (ticket.qty or 1)),
                        summary=f"{ticket.sku}: cost ${cost:.2f}, list ${lst:.2f}.",
                    )

            if ticket.invoice_id:
                r = con.execute(
                    "SELECT i.*, v.name AS vendor_name, v.specialty, v.lead_days "
                    "FROM invoices i JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?",
                    (ticket.invoice_id,),
                ).fetchone()
                if r:
                    invoice = dict(r)
                    invoice["amount"] = money(invoice["amount"])
                    from datetime import date as _d

                    due = _d.fromisoformat(invoice["due_date"][:10])
                    invoice["days_until_due"] = (due - now).days
                    invoice["is_overdue"] = (due - now).days < 0
                    invoice["expected_delivery_date"] = (
                        due + timedelta(days=invoice["lead_days"])
                    ).isoformat()

            if ticket.lease_id:
                r = con.execute(
                    "SELECT * FROM leases WHERE id = ?", (ticket.lease_id,)
                ).fetchone()
                if r:
                    lease = dict(r)
                    lease["monthly_rent"] = money(lease["monthly_rent"])
                    from datetime import date as _d

                    lease["days_until_due"] = (
                        _d.fromisoformat(lease["next_due"][:10]) - now
                    ).days

        bits = [f"Ticket #{ticket.ticket_id} ({ticket.type}, {ticket.status}) from {ticket.requester}: {ticket.subject}."]
        if ticket.notes:
            bits.append(f'Notes: "{ticket.notes}"')
        if stock:
            bits.append("Stock: " + ", ".join(f"{s.size}={s.qty}" for s in stock) + ".")
        if pricing:
            bits.append(f"Price: ${pricing.list_price:.2f} list, ${pricing.unit_cost:.2f} cost.")
        if invoice:
            bits.append(
                f"Linked invoice #{invoice['id']}: ${invoice['amount']:.2f} to "
                f"{invoice['vendor_name']}, due {invoice['due_date']}, "
                f"{'OVERDUE' if invoice['is_overdue'] else 'not yet due'}, "
                f'"{invoice.get("description") or ""}".'
            )
        if lease:
            bits.append(
                f"Linked lease #{lease['id']}: ${lease['monthly_rent']:.2f}/month to "
                f"{lease['landlord']}, next due {lease['next_due']}."
            )

        return TicketDetail(
            found=True, ticket=ticket, linked_stock=stock, linked_pricing=pricing,
            linked_invoice=invoice, linked_lease=lease, summary=" ".join(bits),
        )

    # ------------------------------------------------------------------ #
    # 6. find_vendor
    # ------------------------------------------------------------------ #

    @mcp.tool
    def find_vendor(specialty: str | None = None) -> VendorList:
        """Find suppliers, their turnaround times, and what they are already owed.

        Use this to route a restock to a supplier that actually makes the category, and
        to get the `lead_days` needed to quote a realistic restock date. The unpaid-bill
        totals matter: a vendor owed money may not prioritise a rush job.

        Args:
            specialty: Substring match on the vendor's specialty, e.g. "apparel" or
                "courier". Omit to list every vendor.

        Returns:
            VendorList. An empty list means no vendor matched — do not substitute one.
        """
        with closing(connect()) as con:
            if specialty:
                cur = con.execute(
                    "SELECT * FROM vendors WHERE LOWER(specialty) LIKE ? ORDER BY lead_days",
                    (f"%{specialty.strip().lower()}%",),
                )
            else:
                cur = con.execute("SELECT * FROM vendors ORDER BY lead_days")
            vendors = []
            for r in cur:
                owed = con.execute(
                    "SELECT COUNT(*) AS n, COALESCE(SUM(amount),0) AS total FROM invoices "
                    "WHERE vendor_id = ? AND LOWER(status) != 'paid'",
                    (r["id"],),
                ).fetchone()
                vendors.append(
                    VendorInfo(
                        vendor_id=r["id"], name=r["name"], specialty=r["specialty"],
                        lead_days=r["lead_days"], open_invoice_count=owed["n"],
                        open_invoice_total=money(owed["total"]),
                    )
                )

        if not vendors:
            return VendorList(
                found=False, query=specialty, vendors=[],
                summary=f"No vendor matches specialty {specialty!r}. None was substituted.",
            )
        desc = "; ".join(
            f"{v.name} ({v.specialty}, {v.lead_days}d lead"
            + (f", owed ${v.open_invoice_total:.2f}" if v.open_invoice_count else "")
            + ")"
            for v in vendors
        )
        return VendorList(
            found=True, query=specialty, vendors=vendors,
            summary=f"{len(vendors)} vendor(s): {desc}.",
        )

    # ------------------------------------------------------------------ #
    # 7. record_payment  (WRITE)
    # ------------------------------------------------------------------ #

    @mcp.tool
    def record_payment(
        kind: str,
        ref_id: int,
        amount: float,
        account: str,
        approved_by: str,
        memo: str | None = None,
    ) -> PaymentResult:
        """Pay a vendor invoice or a rent obligation, and record it in the ledger.

        This moves real money. It is refused — with nothing written — if any of the
        following is true, so check `ok` before telling anyone a bill is settled:

        - the invoice or lease does not exist;
        - the invoice is already marked paid, or a payment already exists for this
          obligation (no double payment);
        - `amount` does not equal the amount actually owed (no partial or over payment);
        - the account does not exist, or the balance would go negative (no overdraft);
        - `approved_by` is empty (every payment names a human approver).

        On success it appends one row to `payments`, decrements the account balance, and
        marks an invoice paid — in a single transaction.

        Args:
            kind: "invoice" or "rent".
            ref_id: The invoices.id or the leases.id being settled.
            amount: Exact amount owed. Must match the ledger.
            account: Cash account name, e.g. "checking".
            approved_by: Name of the person authorising this payment. Required.
            memo: Optional short note stored with the ticket trail.

        Returns:
            PaymentResult with balance before and after, or `ok = False` and a
            `refusal_reason` explaining what was wrong.
        """
        kind_key = (kind or "").strip().lower()
        approver = (approved_by or "").strip()

        if kind_key not in VALID_PAYMENT_KINDS:
            return PaymentResult(
                ok=False, action="record_payment", refusal_reason="invalid_kind",
                message=f"kind must be one of {sorted(VALID_PAYMENT_KINDS)}, got {kind!r}.",
            )
        if not approver:
            return PaymentResult(
                ok=False, action="record_payment", refusal_reason="no_approver",
                message="approved_by is required. No payment may be recorded without a named approver.",
            )

        with closing(connect()) as con:
            now = today(con)

            dup = con.execute(
                "SELECT id, amount, paid_at FROM payments WHERE LOWER(kind) = ? AND ref_id = ?",
                (kind_key, ref_id),
            ).fetchone()
            if dup:
                return PaymentResult(
                    ok=False, action="record_payment", refusal_reason="already_paid",
                    message=(
                        f"{kind_key} {ref_id} was already paid by payment #{dup['id']} "
                        f"(${money(dup['amount']):.2f} on {dup['paid_at']}). Refusing to pay twice."
                    ),
                )

            if kind_key == "invoice":
                rec = con.execute("SELECT * FROM invoices WHERE id = ?", (ref_id,)).fetchone()
                if rec is None:
                    return PaymentResult(
                        ok=False, action="record_payment", refusal_reason="ref_not_found",
                        message=f"No invoice with id {ref_id}. Nothing was paid.",
                    )
                if str(rec["status"]).lower() == "paid":
                    return PaymentResult(
                        ok=False, action="record_payment", refusal_reason="already_paid",
                        message=f"Invoice {ref_id} is already marked paid. Refusing to pay twice.",
                    )
                owed = money(rec["amount"])
                label = f"invoice {ref_id}"
            else:
                rec = con.execute("SELECT * FROM leases WHERE id = ?", (ref_id,)).fetchone()
                if rec is None:
                    return PaymentResult(
                        ok=False, action="record_payment", refusal_reason="ref_not_found",
                        message=f"No lease with id {ref_id}. Nothing was paid.",
                    )
                owed = money(rec["monthly_rent"])
                label = f"rent on lease {ref_id}"

            if money(amount) != owed:
                return PaymentResult(
                    ok=False, action="record_payment", refusal_reason="amount_mismatch",
                    message=(
                        f"Refusing to pay ${money(amount):.2f} for {label}: the ledger says "
                        f"${owed:.2f} is owed. Pay the exact amount on file."
                    ),
                    changes={"amount_requested": money(amount), "amount_owed": owed},
                )

            acct = con.execute(
                "SELECT * FROM cash_accounts WHERE LOWER(name) = ?", (account.strip().lower(),)
            ).fetchone()
            if acct is None:
                return PaymentResult(
                    ok=False, action="record_payment", refusal_reason="account_not_found",
                    message=f"No cash account named {account!r}. Nothing was paid.",
                )

            before = money(acct["balance"])
            after = money(before - owed)
            if after < 0:
                return PaymentResult(
                    ok=False, action="record_payment", refusal_reason="insufficient_funds",
                    message=(
                        f"Refusing to overdraw {acct['name']}: paying ${owed:.2f} against a "
                        f"${before:.2f} balance would leave ${after:.2f}. Escalate instead."
                    ),
                    balance_before=before,
                    changes={"balance_before": before, "would_be": after},
                )

            paid_at = f"{now.isoformat()}T12:00:00-04:00"
            try:
                with con:
                    cur = con.execute(
                        "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) "
                        "VALUES (?,?,?,?,?,?)",
                        (kind_key, ref_id, owed, acct["name"], paid_at, approver),
                    )
                    payment_id = cur.lastrowid
                    con.execute(
                        "UPDATE cash_accounts SET balance = ? WHERE name = ?",
                        (after, acct["name"]),
                    )
                    if kind_key == "invoice":
                        con.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (ref_id,))
            except sqlite3.Error as exc:
                return PaymentResult(
                    ok=False, action="record_payment", refusal_reason="write_failed",
                    message=f"Database refused the write, nothing changed: {exc}",
                )

        return PaymentResult(
            ok=True, action="record_payment", payment_id=payment_id, amount_paid=owed,
            account=acct["name"], balance_before=before, balance_after=after,
            message=(
                f"Paid ${owed:.2f} for {label} from {acct['name']}, approved by {approver}. "
                f"Balance ${before:.2f} -> ${after:.2f}."
                + (f" Memo: {memo}" if memo else "")
            ),
            changes={
                "payments": f"+1 row (id {payment_id})",
                "cash_accounts.balance": f"{before} -> {after}",
                **({"invoices.status": "open -> paid"} if kind_key == "invoice" else {}),
            },
        )

    # ------------------------------------------------------------------ #
    # 8. adjust_stock  (WRITE)
    # ------------------------------------------------------------------ #

    @mcp.tool
    def adjust_stock(sku: str, size: str, delta: int, reason: str) -> ActionResult:
        """Change the units on hand for one (sku, size), up or down.

        Use a negative delta to commit stock to a customer and a positive one to book a
        delivery in. Refused, with nothing written, if the row does not exist or if the
        change would drive stock below zero — the shop cannot hold negative inventory,
        and an agent must not paper over a shortfall.

        Args:
            sku: Product code, e.g. "CC-HOOD-NAVY".
            size: Exact size, e.g. "M". Stock is tracked per size.
            delta: Units to add (positive) or remove (negative).
            reason: Short justification, recorded in the result. Required.

        Returns:
            ActionResult with before/after quantities, or `ok = False` and a reason.
        """
        if not (reason or "").strip():
            return ActionResult(
                ok=False, action="adjust_stock", refusal_reason="no_reason",
                message="A reason is required for every stock adjustment.",
            )
        if delta == 0:
            return ActionResult(
                ok=False, action="adjust_stock", refusal_reason="no_op",
                message="delta of 0 changes nothing; no adjustment recorded.",
            )

        sku_key, size_key = sku.strip().upper(), size.strip().upper()
        with closing(connect()) as con:
            row = con.execute(
                "SELECT * FROM inventory WHERE UPPER(sku) = ? AND UPPER(size) = ?",
                (sku_key, size_key),
            ).fetchone()
            if row is None:
                return ActionResult(
                    ok=False, action="adjust_stock", refusal_reason="row_not_found",
                    message=f"No inventory row for {sku_key} size {size_key}. Nothing changed.",
                )
            before = row["qty"]
            after = before + delta
            if after < 0:
                return ActionResult(
                    ok=False, action="adjust_stock", refusal_reason="would_go_negative",
                    message=(
                        f"Refusing to move {sku_key} {size_key} from {before} by {delta}: "
                        f"that would leave {after}. Only {before} unit(s) exist."
                    ),
                    changes={"qty_before": before, "would_be": after},
                )
            with con:
                con.execute(
                    "UPDATE inventory SET qty = ? WHERE sku = ? AND size = ?",
                    (after, row["sku"], row["size"]),
                )

        return ActionResult(
            ok=True, action="adjust_stock",
            message=(
                f"{row['name']} ({sku_key}) size {size_key}: {before} -> {after} "
                f"({delta:+d}). Reason: {reason.strip()}"
            ),
            changes={"sku": sku_key, "size": size_key, "qty_before": before,
                     "qty_after": after, "delta": delta, "reason": reason.strip()},
        )

    # ------------------------------------------------------------------ #
    # 9. resolve_ticket  (WRITE)
    # ------------------------------------------------------------------ #

    @mcp.tool
    def resolve_ticket(ticket_id: int, status: str, resolution_note: str) -> ActionResult:
        """Close out a ticket with a status and a note explaining the outcome.

        Only call this once the work is actually done or a decision has been made. The
        note is the record a human auditor reads later, so it must say what was decided
        and why — not merely "handled".

        Args:
            ticket_id: The ticket being closed.
            status: One of "resolved", "declined", "escalated", "blocked".
            resolution_note: What was decided and why. Required.

        Returns:
            ActionResult, or `ok = False` if the ticket or status is invalid.
        """
        note = (resolution_note or "").strip()
        status_key = (status or "").strip().lower()
        if status_key not in VALID_TICKET_STATUS or status_key == "open":
            return ActionResult(
                ok=False, action="resolve_ticket", refusal_reason="invalid_status",
                message=f"status must be one of resolved/declined/escalated/blocked, got {status!r}.",
            )
        if not note:
            return ActionResult(
                ok=False, action="resolve_ticket", refusal_reason="no_note",
                message="A resolution note is required so the decision can be audited later.",
            )

        with closing(connect()) as con:
            row = con.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            if row is None:
                return ActionResult(
                    ok=False, action="resolve_ticket", refusal_reason="ticket_not_found",
                    message=f"No ticket with id {ticket_id}. Nothing changed.",
                )
            before_status = row["status"]
            before_notes = row["notes"] or ""
            merged = (before_notes + "\n" if before_notes else "") + f"[resolution] {note}"
            with con:
                con.execute(
                    "UPDATE tickets SET status = ?, notes = ? WHERE id = ?",
                    (status_key, merged, ticket_id),
                )

        return ActionResult(
            ok=True, action="resolve_ticket",
            message=f"Ticket #{ticket_id}: {before_status} -> {status_key}. {note}",
            changes={"ticket_id": ticket_id, "status_before": before_status,
                     "status_after": status_key, "resolution_note": note},
        )

    # ------------------------------------------------------------------ #
    # 10. post_desk_note  (WRITE — the shared workspace)
    # ------------------------------------------------------------------ #

    @mcp.tool
    def post_desk_note(author: str, note: str) -> ActionResult:
        """Append a line to the shared desk notes — the team's common workspace.

        Every agent reads and writes the same `desk.notes` field, so this is how one
        specialist leaves a finding for another and how the shift hands off to the next
        run. Notes are **appended**; nothing already written is overwritten.

        Args:
            author: Which agent or person is writing, e.g. "accounting".
            note: The line to record. Keep it to one or two sentences.

        Returns:
            ActionResult containing the full note log after the append.
        """
        text, who = (note or "").strip(), (author or "").strip()
        if not text or not who:
            return ActionResult(
                ok=False, action="post_desk_note", refusal_reason="empty_note",
                message="Both author and note are required.",
            )

        with closing(connect()) as con:
            now = today(con)
            row = con.execute("SELECT notes FROM desk LIMIT 1").fetchone()
            existing = (row["notes"] if row and row["notes"] else "").rstrip()
            line = f"[{now.isoformat()}] {who}: {text}"
            merged = f"{existing}\n{line}" if existing else line
            with con:
                con.execute("UPDATE desk SET notes = ?", (merged,))

        return ActionResult(
            ok=True, action="post_desk_note",
            message=f"Noted on the shared desk: {line}",
            changes={"appended": line, "total_lines": len(merged.splitlines())},
        )


def today_str(d) -> str:
    return d.isoformat()
