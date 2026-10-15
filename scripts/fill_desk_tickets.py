"""Fill the Actual, Cash, and Reflections sections of output/desk_tickets.html.

The Expected sections written in Task 6 are left exactly as they were — the point of
that file is the comparison, so rewriting a prediction after seeing the result would
destroy its only value.

Run from the HW 5 folder:  python scripts/fill_desk_tickets.py
"""

from __future__ import annotations

import re
from pathlib import Path

HW5 = Path(__file__).resolve().parent.parent
PAGE = HW5 / "output" / "desk_tickets.html"

ACTUAL_101 = """
        <div class="first-call">
          <div class="label">Boss's first call — as predicted</div>
          <code class="tool">get_ticket(ticket_id=101)</code>
          <p class="why" style="margin-top:8px">
            The boss opened with <code>get_ticket</code> exactly as expected, and that one
            call carried the ticket, the <code>S = 0</code> stock row, the $28.00/$8.00
            pricing, and invoice <b>501</b> joined to Bulldog Print Co. It never needed a
            second orientation call.
          </p>
        </div>

        <h4 class="step">Delegations that actually happened</h4>
        <ol class="deleg">
          <li>
            <span class="ask"><code class="agent">ask_inventory</code> — 1st, as predicted</span>
            <span class="says"><em>Boss actually asked</em>“For ticket #101, CC-TEE-WHITE size S has
              stock 0 with shortfall 1. Linked invoice #501 is an overdue $840 rush reprint to
              Bulldog Print Co, expected delivery 2026-09-02. Can this order be filled after
              that reprint, and is the expected date still valid?”</span>
            <span class="why"><b>Tools it used:</b> <code class="tool">get_ticket</code>,
              <code class="tool">find_vendor("apparel")</code>.
              <br><b>Reported:</b> stock 0, shortfall 1; invoice 501 is specifically a reprint
              of CC-TEE-WHITE S so the order can be filled once received — but
              <i>the invoice record does not confirm the delivery date</i>.</span>
          </li>
          <li>
            <span class="ask"><code class="agent">ask_accounting</code> — 2nd, as predicted</span>
            <span class="says"><em>Boss actually asked</em>“Should the shop pay this invoice now to
              help unblock the reprint, or does the cash/payment data require human
              approval?”</span>
            <span class="why"><b>Tools it used:</b> <code class="tool">get_ticket</code>,
              <code class="tool">get_cash_and_obligations</code>.
              <br><b>Reported:</b> $3,400.00 cash; invoice 501 overdue by 3 days at $840.00;
              rent $2,400.00 due in 2 days; <b>paying both leaves $160.00</b>, so the decision
              needs human approval.</span>
          </li>
          <li>
            <span class="ask"><code class="agent">ask_customer_service</code> — 3rd and last, as predicted</span>
            <span class="says"><em>Boss actually asked</em>“…delivery is expected 2026-09-02 but not
              confirmed. Draft an accurate customer reply without promising fulfillment.”</span>
            <span class="why"><b>Tools it used:</b> <code class="tool">get_ticket</code>.
              <br><b>Reported:</b> size S is out of stock and the reprint date is unconfirmed —
              <i>fulfilment should not be promised</i>. All four facts it cited were tagged
              back to <code>get_ticket</code>.</span>
          </li>
        </ol>

        <h4 class="step">MCP tools actually called</h4>
        <table class="tools">
          <tr><th>Tool</th><th>Called by</th><th>Actual result</th></tr>
          <tr><td><code class="tool">get_ticket</code></td><td>boss, inventory, accounting, customer_service</td><td>Ticket + stock S=0 + pricing + invoice 501 + vendor, in one call each</td></tr>
          <tr><td><code class="tool">find_vendor</code></td><td>inventory</td><td>Bulldog Print Co, apparel reprint, 5 lead days, owed $840.00</td></tr>
          <tr><td><code class="tool">get_cash_and_obligations</code></td><td>accounting</td><td>$3,400 cash · $840 overdue · $2,400 rent · $160 remaining</td></tr>
          <tr><td><code class="tool">resolve_ticket</code> <b>(write)</b></td><td>boss</td><td>101 → <code>escalated</code></td></tr>
        </table>

        <div class="notexpected" style="background:#eef8f2;border-color:#cfe8da">
          <div class="label" style="color:#1d7a4c">Predictions that held</div>
          <ul>
            <li><code>check_stock</code> was predicted for inventory. It was <b>not</b> called — <code>get_ticket</code> already returned the linked stock row, so inventory skipped the extra round trip. The prediction named the right fact, the wrong tool.</li>
            <li><code>record_payment</code> and <code>adjust_stock</code> were predicted <b>not</b> to be called by the agents. Correct — neither was.</li>
            <li>Facilities was predicted to be skipped. Correct.</li>
          </ul>
        </div>

        <div class="outcome">
          <div class="label">Actual disposition and money</div>
          Agent closed it <b>escalated</b>, moving <b>$0.00</b> — as predicted. A human then
          approved <b>$840.00</b> to invoice 501 and booked <b>12</b> tees in, and the ticket
          was closed <b>resolved</b>. 41,282 tokens across 13 model requests.
        </div>

        <div class="outcome" style="background:#fdf8e9;border-color:#eadfba">
          <div class="label" style="color:#8a6d1f">Manual approvals</div>
          <b>Payment</b> — <code>record_payment(invoice, 501, $840.00)</code>, approved by
          Alexandria Rosenzweig. Balance $3,400.00 → $2,560.00.<br>
          <b>Purchase</b> — <code>adjust_stock(CC-TEE-WHITE, S, +12)</code>, reprint received.
          Stock 0 → 12. No cash effect; the $840 was the invoice, not the goods.
        </div>
"""

ACTUAL_102 = """
        <div class="first-call">
          <div class="label">Boss's first call — as predicted</div>
          <code class="tool">get_ticket(ticket_id=102)</code>
          <p class="why" style="margin-top:8px">
            As predicted, the ticket's <code>lease_id = 1</code> meant this call also returned
            the lease — landlord, $2,400.00 monthly rent, next due 2026-09-02 — before any
            desk was asked anything.
          </p>
        </div>

        <h4 class="step">Delegations that actually happened</h4>
        <ol class="deleg">
          <li>
            <span class="ask"><code class="agent">ask_facilities</code> — 1st, as predicted</span>
            <span class="says"><em>Boss actually asked</em>“For lease 1 at the Chapel Street shop,
              landlord Elm City Properties, monthly rent $2400.00, next due 2026-09-02 (2 days):
              is the rent notice genuine and what does the lease require?”</span>
            <span class="why"><b>Tools it used:</b> <code class="tool">get_cash_and_obligations</code>.
              <br><b>Reported:</b> lease 1 confirms Elm City Properties, $2,400.00, next due
              2026-09-02, 2 days remaining as of 2026-08-31 — and, going further than the
              prediction, that <i>the notice itself cannot be independently authenticated
              beyond the matching lease record</i>.</span>
          </li>
          <li>
            <span class="ask"><code class="agent">ask_accounting</code> — 2nd, as predicted</span>
            <span class="says"><em>Boss actually asked</em>“For the verified lease 1 rent due
              2026-09-02, amount $2400.00 to Elm City Properties, can the shop afford payment
              now, and should it be paid now?”</span>
            <span class="why"><b>Tools it used:</b> <code class="tool">get_cash_and_obligations</code>.
              <br><b>Reported:</b> $3,400.00 in checking; the rent is technically coverable, but
              an overdue $840.00 invoice is outstanding on the same account and
              <b>paying both leaves only $160.00</b>.</span>
          </li>
        </ol>

        <p class="why" style="margin-top:14px"><b>Two desks, exactly as predicted.</b> Inventory
          and customer service were never consulted — no product, and the landlord is not a
          customer awaiting a drafted reply.</p>

        <h4 class="step">MCP tools actually called</h4>
        <table class="tools">
          <tr><th>Tool</th><th>Called by</th><th>Actual result</th></tr>
          <tr><td><code class="tool">get_ticket</code></td><td>boss</td><td>Ticket 102 with lease 1 attached</td></tr>
          <tr><td><code class="tool">get_cash_and_obligations</code></td><td>facilities, accounting</td><td>Lease + landlord match + $3,400 cash + $840 overdue + $160 remaining</td></tr>
          <tr><td><code class="tool">resolve_ticket</code> <b>(write)</b></td><td>boss</td><td>102 → <code>escalated</code></td></tr>
        </table>

        <div class="notexpected" style="background:#eef8f2;border-color:#cfe8da">
          <div class="label" style="color:#1d7a4c">Predictions that held, and one that was beaten</div>
          <ul>
            <li>Facilities before accounting — <b>correct</b>.</li>
            <li>Only two desks consulted — <b>correct</b>.</li>
            <li><code>record_payment</code> not called by the agents — <b>correct</b>.</li>
            <li><b>Beaten:</b> the prediction said facilities would confirm the requester matches <code>leases.landlord</code>. It did better — it reported the match <i>and</i> flagged that the database holds no record of the email itself, so the notice cannot be authenticated beyond that coincidence of names. That limitation was not predicted.</li>
          </ul>
        </div>

        <div class="outcome">
          <div class="label">Actual disposition and money</div>
          Agent closed it <b>escalated</b>, moving <b>$0.00</b> — as predicted. A human then
          approved the verified <b>$2,400.00</b> rent and the ticket was closed
          <b>resolved</b>. 22,577 tokens across 8 model requests — the cheapest of the three.
        </div>

        <div class="outcome" style="background:#fdf8e9;border-color:#eadfba">
          <div class="label" style="color:#8a6d1f">Manual approvals</div>
          <b>Payment</b> — <code>record_payment(rent, lease 1, $2,400.00)</code>, approved by
          Alexandria Rosenzweig. Balance $2,560.00 → $160.00. The figure came from
          <code>leases.monthly_rent</code>, not from the email, which named no amount.
        </div>
"""

ACTUAL_103 = """
        <div class="first-call">
          <div class="label">Boss's first call — as predicted</div>
          <code class="tool">get_ticket(ticket_id=103)</code>
          <p class="why" style="margin-top:8px">
            The single call returned stock <code>M = 8</code> and pricing $22.00/$58.00
            together, so the boss saw the 12-unit shortfall before routing — exactly the
            reason the prediction gave for opening here.
          </p>
        </div>

        <h4 class="step">Delegations that actually happened</h4>
        <ol class="deleg">
          <li>
            <span class="ask"><code class="agent">ask_inventory</code> — 1st, as predicted</span>
            <span class="says"><em>Boss actually asked</em>“For ticket #103, CC-HOOD-NAVY size M has
              8 in stock for a requested quantity of 20 (shortfall 12). Can we supply the
              missing 12, and if so when? Is any reprint or restock already on order?”</span>
            <span class="why"><b>Tools it used:</b> <code class="tool">get_ticket</code>,
              <code class="tool">find_vendor("apparel")</code>.
              <br><b>Reported:</b> 8 on hand against 20, shortfall 12; <b>no restock is on
              order</b> (<code>invoice_id = null</code>); apparel lead time 5 days.</span>
          </li>
          <li>
            <span class="ask"><code class="agent">ask_accounting</code> — 2nd, as predicted</span>
            <span class="says"><em>Boss actually asked</em>“What bulk unit price, if any, clears cost
              and is acceptable, and should this discount be escalated given the reprint?”</span>
            <span class="why"><b>Tools it used:</b> <code class="tool">get_ticket</code>,
              <code class="tool">get_price_and_margin(qty=20, proposed_unit_price=50)</code>,
              <code class="tool">get_cash_and_obligations</code>.
              <br><b>Reported:</b> <b>$50.00/unit clears cost</b> — $8.00 (13.79%) off the
              $58.00 list, $28.00 margin per hoodie, $560.00 on 20 units. It chose the $50
              figure itself; the prediction only said it would test one.</span>
          </li>
          <li>
            <span class="ask"><code class="agent">ask_customer_service</code> — 3rd and last, as predicted</span>
            <span class="says"><em>Boss actually asked</em>“…8 are on hand and 12 require a reprint
              with a 5-day vendor lead time. $50 per hoodie clears the $22 cost.”</span>
            <span class="why"><b>Tools it used:</b> <code class="tool">get_ticket</code>.
              <br><b>Reported:</b> 8 on hand against 20, list $58.00, and
              <i>no bulk quote recorded yet</i> — it refused to state a quote the database
              could not back.</span>
          </li>
        </ol>

        <h4 class="step">MCP tools actually called</h4>
        <table class="tools">
          <tr><th>Tool</th><th>Called by</th><th>Actual result</th></tr>
          <tr><td><code class="tool">get_ticket</code></td><td>boss, inventory, accounting, customer_service</td><td>Stock M=8 and pricing $22/$58 in one call</td></tr>
          <tr><td><code class="tool">find_vendor</code></td><td>inventory</td><td>Bulldog Print Co, 5 lead days, owed $840.00</td></tr>
          <tr><td><code class="tool">get_price_and_margin</code></td><td>accounting</td><td>$50.00 × 20 → $28.00/unit margin, <code>above_cost = true</code></td></tr>
          <tr><td><code class="tool">get_cash_and_obligations</code></td><td>accounting</td><td>$3,400 cash; vendor carries an overdue $840 invoice</td></tr>
          <tr><td><code class="tool">resolve_ticket</code> <b>(write)</b></td><td>boss</td><td>103 → <code>escalated</code></td></tr>
        </table>

        <div class="notexpected">
          <div class="label">Where the prediction was wrong</div>
          <ul>
            <li><b>The prediction said <code>get_cash_and_obligations</code> would NOT be called</b> — "this is a margin question, not a cash-position question." Accounting called it anyway, and was right to: it wanted to know whether the vendor who would print the missing 12 was already owed money. It was — $840, overdue. The prediction treated the ticket as self-contained; the agent found the link to ticket 101.</li>
            <li><code>check_stock</code> was predicted but not called — <code>get_ticket</code> had already returned the stock row. Same substitution as ticket 101.</li>
            <li><code>adjust_stock</code> and <code>record_payment</code> correctly not called.</li>
          </ul>
        </div>

        <div class="outcome">
          <div class="label">Actual disposition and money</div>
          Agent closed it <b>escalated</b> rather than the predicted <b>declined</b>, moving
          <b>$0.00</b>. A human then closed it <b>resolved</b>: the 20-unit order declined,
          the 8 in stock offered at $50.00/unit. 43,259 tokens across 14 model requests —
          the most expensive of the three, and the only one to use four distinct tools.
        </div>

        <div class="outcome" style="background:#f7f9fc">
          <div class="label">Manual approvals</div>
          <b>None required.</b> An outbound sale moves no money out of the shop, and stock was
          deliberately not committed with <code>adjust_stock</code> — reserving the 8 before
          the Yale AI Club accepts would strand inventory another customer could buy.
        </div>
"""

CASH_TAB = """
    <h2>Cash</h2>
    <p class="sub">Every movement for the shift of 2026-08-31, reconciled against
      <code>cash_accounts</code>.</p>

    <section class="block expected">
      <h3>Itemised ledger <span class="pill">RECONCILED</span></h3>
      <div class="body">
        <table class="tools">
          <tr>
            <th>Ticket</th><th>Movement</th><th>Why</th>
            <th style="text-align:right">Amount</th><th style="text-align:right">Balance</th>
          </tr>
          <tr style="background:#f7f9fc">
            <td>—</td>
            <td><b>Opening balance</b><div style="color:var(--muted);font-size:13px">after resetting to the original data pack</div></td>
            <td style="color:var(--muted)">Starting position for the shift</td>
            <td style="text-align:right;color:var(--muted)">—</td>
            <td style="text-align:right;font-weight:700;font-variant-numeric:tabular-nums">$3,400.00</td>
          </tr>
          <tr>
            <td><b>#101</b></td>
            <td>Paid <b>invoice 501</b> to Bulldog Print Co<div style="color:var(--muted);font-size:13px"><code>record_payment(invoice, 501)</code></div></td>
            <td>The rush reprint of CC-TEE-WHITE size S that ticket 101's customer is waiting on. It was <b>3 days overdue</b> (due 2026-08-28), and a vendor owed money is not reliably going to rush the job.</td>
            <td style="text-align:right;color:#a33a3a;font-variant-numeric:tabular-nums">−$840.00</td>
            <td style="text-align:right;font-variant-numeric:tabular-nums">$2,560.00</td>
          </tr>
          <tr>
            <td><b>#101</b></td>
            <td>Booked <b>12 tees</b> into stock<div style="color:var(--muted);font-size:13px"><code>adjust_stock(CC-TEE-WHITE, S, +12)</code></div></td>
            <td><b>A purchase of goods, not of cash.</b> The $840 above bought these units; receiving them moves inventory, not money. CC-TEE-WHITE size S went 0 → 12.</td>
            <td style="text-align:right;color:var(--muted);font-variant-numeric:tabular-nums">$0.00</td>
            <td style="text-align:right;font-variant-numeric:tabular-nums">$2,560.00</td>
          </tr>
          <tr>
            <td><b>#102</b></td>
            <td>Paid <b>rent</b> on lease 1<div style="color:var(--muted);font-size:13px"><code>record_payment(rent, lease 1)</code></div></td>
            <td>Rent to Elm City Properties, due 2026-09-02. The amount came from <code>leases.monthly_rent</code>, <b>not</b> from the emailed notice — which named no figure at all.</td>
            <td style="text-align:right;color:#a33a3a;font-variant-numeric:tabular-nums">−$2,400.00</td>
            <td style="text-align:right;font-variant-numeric:tabular-nums">$160.00</td>
          </tr>
          <tr>
            <td><b>#103</b></td>
            <td><b>No purchase</b></td>
            <td>An outbound sale: the Yale AI Club would pay the shop, not the reverse. The 20-unit order was declined on supply and no restock was ordered, so nothing left the account.</td>
            <td style="text-align:right;color:var(--muted);font-variant-numeric:tabular-nums">$0.00</td>
            <td style="text-align:right;font-variant-numeric:tabular-nums">$160.00</td>
          </tr>
          <tr style="background:#eef8f2">
            <td></td>
            <td><b>Closing balance</b></td>
            <td style="color:#1d7a4c">Matches <code>cash_accounts.balance</code></td>
            <td style="text-align:right;font-weight:700;font-variant-numeric:tabular-nums">−$3,240.00</td>
            <td style="text-align:right;font-weight:700;font-size:16px;font-variant-numeric:tabular-nums">$160.00</td>
          </tr>
        </table>

        <div class="first-call" style="margin-top:18px">
          <div class="label">Arithmetic check</div>
          <code style="font-size:15px">$3,400.00 − $840.00 − $2,400.00 = $160.00</code>
          <p class="why" style="margin-top:8px">
            Verified directly against the database:
            <code>SELECT balance FROM cash_accounts WHERE name='checking'</code> returns
            <b>160.0</b>. Two rows exist in <code>payments</code>, both approved by
            <b>Alexandria Rosenzweig</b>: <code>#1 invoice 501 $840.00</code> and
            <code>#2 rent lease 1 $2,400.00</code>. No third payment exists, because ticket
            103 moved no money.
          </p>
        </div>

        <div class="notexpected" style="background:#fdf8e9;border-color:#eadfba">
          <div class="label" style="color:#8a6d1f">What the agents did with this money: nothing</div>
          <ul>
            <li>All three runs ended with <b>$0.00 moved</b>. Every dollar above was released by a named human after the team escalated.</li>
            <li>Accounting reached the $160 figure on <b>two separate tickets</b> (101 and 102) and refused to spend on both, because the same $3,400 account was backing two obligations at once.</li>
            <li>The closing $160 is a <b>4.7% buffer</b> against a $3,400 opening position. That is the number the agents kept escalating about, and it turned out to be exactly right.</li>
          </ul>
        </div>
      </div>
    </section>
"""


def fill_actual(html: str, panel_id: str, content: str) -> str:
    """Replace one ticket panel's blank Actual body with the real record."""
    start = html.index(f'id="panel-{panel_id}"')
    marker = html.index('class="block actual"', start)
    body_open = html.index('<div class="body">', marker) + len('<div class="body">')
    # the Actual body ends at the first </div></section> pair after it
    body_close = html.index("      </div>\n    </section>", body_open)
    new_head = html[:marker] + 'class="block actual filled"' + html[marker + len('class="block actual"'):]
    shift = len('class="block actual filled"') - len('class="block actual"')
    return new_head[: body_open + shift] + "\n" + content + "      " + new_head[body_close + shift :]


def main() -> None:
    html = PAGE.read_text(encoding="utf-8")

    for pid, content in (("101", ACTUAL_101), ("102", ACTUAL_102), ("103", ACTUAL_103)):
        html = fill_actual(html, pid, content)

    # swap the TO BE COMPLETED pills on the now-filled Actual sections
    html = html.replace(
        '<h3>Actual <span class="pill">TO BE COMPLETED</span></h3>',
        '<h3>Actual <span class="pill" style="background:#1d7a4c;color:#fff">RECORDED</span></h3>',
    )

    # Cash tab
    cash_old = re.search(
        r'(<div class="panel" role="tabpanel" id="panel-cash".*?>)(.*?)(\n  </div>\n\n  <!-- =+ REFLECTIONS)',
        html, re.S,
    )
    html = html[: cash_old.start(2)] + "\n" + CASH_TAB + html[cash_old.end(2) :]

    PAGE.write_text(html, encoding="utf-8")
    print(f"filled Actual x3 and Cash — {len(html):,} chars")


if __name__ == "__main__":
    main()
