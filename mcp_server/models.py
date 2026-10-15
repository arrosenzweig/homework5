"""Typed return models for the Campus Customs MCP tools.

Every tool returns one of these models rather than free text. The agent therefore
receives named, typed fields it can quote directly, and a missing record comes back
as an explicit `found = False` instead of a plausible-looking guess.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# check_stock
# --------------------------------------------------------------------------- #


class StockRow(BaseModel):
    """One sellable unit: a SKU in a specific size."""

    sku: str
    name: str = Field(description="Product name as recorded in inventory.name.")
    size: str = Field(description="S/M/L/XL for apparel, OS for one-size goods.")
    qty: int = Field(description="Units physically on hand right now.")
    location: str = Field(description="Aisle the unit is picked from.")
    in_stock: bool = Field(description="True when qty > 0.")
    can_fill: bool | None = Field(
        default=None,
        description="Whether qty covers requested_qty. None when no quantity was requested.",
    )
    shortfall: int | None = Field(
        default=None,
        description="Units short of requested_qty; 0 when the request is coverable.",
    )


class StockReport(BaseModel):
    """Result of a stock lookup. `found = False` means the SKU is not in inventory."""

    sku: str
    found: bool
    requested_size: str | None = None
    requested_qty: int | None = None
    rows: list[StockRow] = Field(default_factory=list)
    total_on_hand: int = Field(
        default=0, description="Sum of qty across the returned rows."
    )
    summary: str = Field(description="One line stating exactly what the database holds.")


# --------------------------------------------------------------------------- #
# get_price_and_margin
# --------------------------------------------------------------------------- #


class PriceQuote(BaseModel):
    """Evaluation of a proposed per-unit price against the recorded cost."""

    proposed_unit_price: float
    discount_off_list: float = Field(description="list_price - proposed_unit_price.")
    discount_pct: float = Field(description="Discount as a percentage of list_price.")
    margin_per_unit: float = Field(description="proposed_unit_price - unit_cost.")
    margin_pct: float = Field(description="Margin as a percentage of proposed_unit_price.")
    above_cost: bool = Field(
        description="False when the proposed price is at or below unit_cost, i.e. a loss."
    )
    line_total: float = Field(description="proposed_unit_price * qty.")
    line_margin: float = Field(description="margin_per_unit * qty.")


class PricingReport(BaseModel):
    """Result of a pricing lookup. `found = False` means the SKU has no pricing row."""

    sku: str
    found: bool
    unit_cost: float | None = Field(
        default=None, description="What the shop paid. The floor for any discount."
    )
    list_price: float | None = Field(
        default=None, description="Published sell price. The baseline for any discount."
    )
    margin_per_unit: float | None = Field(
        default=None, description="list_price - unit_cost at full price."
    )
    margin_pct: float | None = Field(
        default=None, description="Full-price margin as a percentage of list_price."
    )
    qty: int = Field(default=1, description="Quantity the figures below were costed for.")
    list_line_total: float | None = Field(
        default=None, description="list_price * qty, with no discount applied."
    )
    quote: PriceQuote | None = Field(
        default=None,
        description="Present only when a proposed_unit_price was supplied for checking.",
    )
    summary: str = Field(description="One line stating exactly what the database holds.")


# --------------------------------------------------------------------------- #
# get_cash_and_obligations
# --------------------------------------------------------------------------- #


class AccountBalance(BaseModel):
    """A cash account as of the date the balance was recorded."""

    name: str
    balance: float
    as_of: str = Field(description="Date the balance was accurate (cash_accounts.date).")


class OpenInvoice(BaseModel):
    """An unpaid vendor bill, with the vendor's turnaround attached."""

    invoice_id: int
    vendor_id: int
    vendor_name: str
    vendor_specialty: str
    vendor_lead_days: int = Field(
        description="Vendor turnaround in days; the basis for any restock ETA."
    )
    amount: float
    due_date: str
    status: str
    description: str | None = Field(
        default=None, description="What the bill covers, verbatim from the invoice."
    )
    days_until_due: int = Field(
        description="Negative when overdue, measured against desk.date_today."
    )
    is_overdue: bool
    expected_delivery_date: str | None = Field(
        default=None,
        description="due_date + vendor_lead_days. When restocking work on this bill lands.",
    )


class LeaseObligation(BaseModel):
    """A rent obligation as recorded on the lease, not as claimed in a notice."""

    lease_id: int
    space_name: str
    landlord: str
    monthly_rent: float = Field(
        description="The authoritative rent amount to verify any notice against."
    )
    next_due: str
    days_until_due: int = Field(
        description="Negative when overdue, measured against desk.date_today."
    )
    is_overdue: bool
    notes: str | None = None


class CashPosition(BaseModel):
    """Everything the shop owes, set against everything it can spend."""

    as_of: str = Field(description="desk.date_today — the dataset's current date.")
    accounts: list[AccountBalance] = Field(default_factory=list)
    total_cash: float
    open_invoices: list[OpenInvoice] = Field(default_factory=list)
    leases: list[LeaseObligation] = Field(default_factory=list)
    total_invoices_due: float
    total_rent_due: float
    total_obligations: float = Field(
        description="total_invoices_due + total_rent_due."
    )
    remaining_if_all_paid: float = Field(
        description="total_cash - total_obligations. Negative means they cannot all be covered."
    )
    can_cover_all: bool
    recorded_payments: int = Field(
        description="Rows already in the payments table, so nothing is paid twice."
    )
    summary: str = Field(description="One line stating exactly what the database holds.")


# --------------------------------------------------------------------------- #
# list_open_tickets / get_ticket
# --------------------------------------------------------------------------- #


class TicketSummary(BaseModel):
    """One row of the work queue, enough to triage and route it."""

    ticket_id: int
    type: str = Field(description="customer_order, rent_notice, or price_override.")
    requester: str
    subject: str
    status: str
    sku: str | None = None
    size: str | None = None
    qty: int | None = None
    lease_id: int | None = None
    invoice_id: int | None = None
    notes: str | None = None
    created_at: str
    age_days: int = Field(description="Days open, measured against desk.date_today.")


class TicketQueue(BaseModel):
    """The open work queue."""

    as_of: str
    count: int
    tickets: list[TicketSummary] = Field(default_factory=list)
    summary: str


class TicketDetail(BaseModel):
    """A single ticket with every record it links to, resolved in one call.

    Returning the linked stock, invoice, and lease rows together means an agent does
    not have to make three more round trips to understand one ticket.
    """

    found: bool
    ticket: TicketSummary | None = None
    linked_stock: list[StockRow] = Field(
        default_factory=list, description="Inventory rows for the ticket's sku/size, if any."
    )
    linked_pricing: PricingReport | None = Field(
        default=None, description="Pricing for the ticket's sku, if any."
    )
    linked_invoice: dict | None = Field(
        default=None, description="The invoice named by invoice_id, with its vendor."
    )
    linked_lease: dict | None = Field(
        default=None, description="The lease named by lease_id."
    )
    summary: str


# --------------------------------------------------------------------------- #
# find_vendor
# --------------------------------------------------------------------------- #


class VendorInfo(BaseModel):
    """A supplier and its turnaround."""

    vendor_id: int
    name: str
    specialty: str
    lead_days: int
    open_invoice_count: int = Field(
        description="Unpaid bills from this vendor. A vendor owed money may not rush work."
    )
    open_invoice_total: float


class VendorList(BaseModel):
    """Suppliers matching a specialty search."""

    found: bool
    query: str | None = None
    vendors: list[VendorInfo] = Field(default_factory=list)
    summary: str


# --------------------------------------------------------------------------- #
# Write-tool results
# --------------------------------------------------------------------------- #


class ActionResult(BaseModel):
    """Outcome of a tool that changes the database.

    `ok = False` means the write was **refused and nothing changed** — the reason is in
    `message`. A refusal is a safe, expected outcome, not an error to retry blindly.
    """

    ok: bool
    action: str = Field(description="Which write was attempted.")
    message: str = Field(description="What happened, or why it was refused.")
    refusal_reason: str | None = Field(
        default=None,
        description="Machine-readable refusal code when ok = False, e.g. 'insufficient_funds'.",
    )
    changes: dict = Field(
        default_factory=dict, description="Before/after values for every field written."
    )


class PaymentResult(ActionResult):
    """Outcome of record_payment, with the resulting ledger position."""

    payment_id: int | None = None
    amount_paid: float | None = None
    account: str | None = None
    balance_before: float | None = None
    balance_after: float | None = None
