"""Fill the Reflections tab of output/desk_tickets.html (Task 10).

Every claim here is tied to the three tickets this app actually ran on 2026-08-31 and
to numbers recorded in output/audit_trail.json.

Run from the HW 5 folder:  python scripts/fill_reflections.py
"""

from __future__ import annotations

import re
from pathlib import Path

PAGE = Path(__file__).resolve().parent.parent / "output" / "desk_tickets.html"

REFLECTIONS = """
    <h2>Reflections</h2>
    <p class="sub">On the shift of 2026-08-31 — tickets 101, 102 and 103. Evidence is in
      the <b>ticket tabs</b> and the <b>Cash tab</b> on this same page.</p>

    <!-- ============ 1. EVALUATION ============ -->
    <section class="block expected">
      <h3>1 · How I would evaluate agent performance <span class="pill">AND WHY</span></h3>
      <div class="body">
        <p class="why" style="margin-bottom:14px">Disposition alone is useless here: all
          three tickets ended <code>escalated</code>, which tells you nothing about whether
          the reasoning was any good. These six measures target the failure modes this
          particular shop actually has.</p>

        <table class="tools">
          <tr><th>Measure</th><th>How it is scored</th><th>This shift</th></tr>
          <tr>
            <td><b>Fact groundedness</b></td>
            <td>Every entry in a desk's <code>facts_used</code> must trace to a
              <code>tool_call</code> in <code>audit_trail.json</code> for that run. A number
              in a report with no matching tool call is a hallucination.</td>
            <td><b>Pass.</b> Inventory cited 3 facts on #101, all from <code>get_ticket</code>
              and <code>find_vendor</code>. Customer service cited 4 on #101, all
              <code>get_ticket</code>.</td>
          </tr>
          <tr>
            <td><b>Trap detection</b></td>
            <td>Each ticket hides one thing that punishes a careless agent. Did it find it?</td>
            <td><b>3 of 3.</b> #101: spotted invoice 501 was <i>already</i> the reprint, avoiding
              a duplicate $840 order. #102: took $2,400 from the lease, not the email, which
              named no amount. #103: checked supply (8 of 20) before pricing.</td>
          </tr>
          <tr>
            <td><b>Spend discipline</b></td>
            <td>Money moved by the agent, versus money a human later judged correct.</td>
            <td><b>$0.00 moved on all three runs.</b> The $3,240 that eventually moved was
              released by a named human. On the evidence of the Cash tab, the agents' caution
              was right: the shift ended on a $160 buffer.</td>
          </tr>
          <tr>
            <td><b>Routing precision</b></td>
            <td>Desks consulted that contributed, over desks consulted. A desk with nothing to
              add still costs a full model round trip.</td>
            <td><b>100%.</b> #102 used 2 desks (facilities, accounting) and skipped inventory
              and customer service — correct, no product and no customer. #101 and #103 used 3
              each and skipped facilities.</td>
          </tr>
          <tr>
            <td><b>Cost per ticket</b></td>
            <td>Tokens and model requests, from the <code>usage</code> records.</td>
            <td>#102 <b>22,577</b> / 8 requests · #101 <b>41,282</b> / 13 · #103 <b>43,259</b> / 14.
              The two-desk ticket cost roughly half the three-desk ones — delegation is the
              dominant cost, not tool calls.</td>
          </tr>
          <tr>
            <td><b>Honest refusal</b></td>
            <td>Does it say "I cannot establish this" rather than filling the gap?</td>
            <td><b>Strong.</b> Facilities volunteered that the notice "cannot be independently
              authenticated beyond the matching lease record". Customer service refused to
              quote a bulk price on #103 because none was recorded yet, and refused to promise
              the unconfirmed 2026-09-02 reprint date on #101.</td>
          </tr>
        </table>

        <p class="why" style="margin-top:14px"><b>Why not accuracy against a gold answer?</b>
          Because there isn't one. Whether to pay $840 when it leaves a $160 buffer is a
          judgement a human owns. What can be graded objectively is whether the agent
          <i>surfaced the right facts and refused to act beyond its authority</i> — which is
          exactly what the six measures above test.</p>
      </div>
    </section>

    <!-- ============ 2. ACTUAL vs EXPECTED ============ -->
    <section class="block actual filled">
      <h3>2 · Actual vs expected, ticket by ticket
        <span class="pill" style="background:#1d7a4c;color:#fff">RECORDED</span></h3>
      <div class="body">
        <p class="why" style="margin-bottom:14px">The predictions were written in Task 6
          <i>before</i> any run. Routing was right all three times; the interesting misses are
          about tools, not sequence.</p>

        <h4 class="step">#101 — Bulldog tee</h4>
        <p class="says"><b>Matched:</b> boss opened with <code>get_ticket</code>, then
          inventory → accounting → customer service last, and escalated with $0 moved.
          Exactly as predicted, in that order.</p>
        <p class="says"><b>Differed:</b> the plan expected inventory to call
          <code>check_stock("CC-TEE-WHITE","S",1)</code>. It never did — <code>get_ticket</code>
          had already returned the linked stock row, so it skipped the extra round trip. The
          prediction named the right <i>fact</i> (qty 0) and the wrong <i>tool</i>. This was a
          design success being mistaken for a miss: <code>get_ticket</code>'s linked records
          exist precisely to collapse those calls.</p>

        <h4 class="step">#102 — Rent due</h4>
        <p class="says"><b>Matched:</b> facilities first, accounting second, only two desks,
          $2,400 verified from <code>leases.monthly_rent</code>, no payment made.</p>
        <p class="says"><b>Differed — the agent beat the plan:</b> the prediction said
          facilities would confirm the requester matches <code>leases.landlord</code>. It did,
          <i>and then said the match proves little</i> — the database holds no copy of the
          email, so the notice "cannot be independently authenticated beyond the matching
          lease record". The plan treated a name match as verification; the agent identified
          it as a coincidence of names. That is a sharper epistemic position than the one I
          wrote for it.</p>

        <h4 class="step">#103 — Bulk hoodie discount</h4>
        <p class="says"><b>Matched:</b> inventory before accounting (the whole point of the
          ticket), shortfall reported as 8 of 20 / short 12, cost floor honoured.</p>
        <p class="says"><b>Differed — the plan was wrong:</b> it explicitly listed
          <code>get_cash_and_obligations</code> under "expected NOT to be called", reasoning
          that a discount is a margin question, not a cash question. Accounting called it
          anyway, to check whether the vendor who would print the missing 12 was already owed
          money. It was — <b>$840, overdue</b>. The plan treated #103 as self-contained; the
          agent found the link to #101. The second difference: predicted <code>declined</code>,
          actual <code>escalated</code> — the agent declined to decline, because the supply
          gap was fixable with a reprint it had no authority to order.</p>

        <div class="notexpected" style="background:#eef8f2;border-color:#cfe8da">
          <div class="label" style="color:#1d7a4c">Pattern across all three</div>
          <ul>
            <li><b>Sequence predictions: 3 of 3 correct.</b> The routing rules in
              <code>boss.md</code> are specific enough to be predictable.</li>
            <li><b>Tool predictions: 2 misses, both the same shape.</b> I over-predicted
              <code>check_stock</code> and under-predicted cross-ticket curiosity. Agents used
              fewer tools than expected for facts and more for context.</li>
          </ul>
        </div>
      </div>
    </section>

    <!-- ============ 3. ONE AGENT ============ -->
    <section class="block expected">
      <h3>3 · Why one agent with tools would have been simpler</h3>
      <div class="body">
        <p class="why">For this workload, a single agent holding all ten MCP tools would have
          been simpler, cheaper and nearly as safe. The evidence is on this page.</p>

        <h4 class="step">The concrete waste</h4>
        <p class="says"><b>Ticket #102 ran the identical tool call twice.</b> Facilities called
          <code>get_cash_and_obligations()</code> with no arguments, and accounting called
          <code>get_cash_and_obligations()</code> with no arguments — the same zero-argument
          call, in the same run, seconds apart, returning identical data. Neither can see the
          other's results, so the second call was pure duplication. One agent calls it once.</p>

        <p class="says"><b>Delegation, not tool use, is where the tokens go.</b> #102 used
          <b>8 model requests</b> for a ticket whose real work was: read the lease, compare to
          the balance. Each <code>ask_*</code> costs a request to compose the question, a full
          nested agent run, and a request to read the report back. A single agent would have
          done #102 in roughly 3 requests. The 22,577-token floor on the simplest ticket is
          almost entirely delegation overhead.</p>

        <p class="says"><b>Six prompt files instead of one.</b> <code>_shared.md</code> plus
          five desk prompts, and the anti-hallucination rules have to be repeated into every
          agent's context on every request. One agent means one prompt loaded once.</p>

        <h4 class="step">What the split actually buys</h4>
        <p class="says">Two things, and it is worth being honest that only one of them is
          structural. <b>Least privilege:</b> customer service cannot move money because
          <code>DESK_TOOLS</code> never shows it <code>record_payment</code> — a real
          guarantee, not a prompt instruction. <b>Separation of verify from pay:</b> facilities
          established the $2,400 and had no payment tool; accounting paid and could not have
          invented the obligation. On #102 that separation did visibly work.</p>

        <p class="says"><b>But the money was never really protected by the agent split.</b> It
          was protected by the MCP write tools, which refuse an overdraft, a double payment, or
          a wrong amount <i>regardless of which agent calls them</i> — as the approval tests
          showed when a human-approved $500 payment against the $840 invoice was still refused.
          The team is defence in depth. The depth is in the tools.</p>

        <div class="outcome">
          <div class="label">Verdict</div>
          At three tickets against a nine-table database, <b>one agent with ten tools wins</b>.
          The team earns its overhead only when desks need genuinely different authority, when
          they can run in parallel rather than in sequence, or when one desk's prompt grows too
          large to sit in a shared context — none of which is true of a shop with four SKUs.
        </div>
      </div>
    </section>

    <!-- ============ 4. SOLVABLE ============ -->
    <section class="block expected">
      <h3>4 · Three new problems our existing tools could already solve</h3>
      <div class="body">
        <h4 class="step">a. Nothing warns anyone a SKU has hit zero</h4>
        <p class="says">On this shift <code>CC-TEE-WHITE</code> size S was at <b>0</b> and
          <code>CC-MUG-CREST</code> is <i>still</i> at <b>0</b> — the mug has had no reprint, no
          invoice, and no ticket. The shop only discovered the tee problem because a customer
          complained. <b>Solvable today:</b> <code>check_stock</code> over each SKU plus
          <code>find_vendor</code> for the lead time plus <code>post_desk_note</code> to leave
          the warning. A scheduled run of the inventory desk alone would produce "CC-MUG-CREST
          OS is at 0; Elm City Gifts, 3-day lead" with no new tools at all.</p>

        <h4 class="step">b. Overdue bills are only noticed when something else touches them</h4>
        <p class="says">Invoice 501 was <b>3 days overdue</b> and surfaced only because ticket
          101 happened to link to it. <code>get_cash_and_obligations</code> already returns
          <code>is_overdue</code> and <code>days_until_due</code> for every unpaid invoice, and
          <code>record_payment</code> already refuses to overdraw. <b>Solvable today:</b> a
          daily accounting run that lists everything overdue and proposes a payment order
          inside the current balance — exactly the reasoning it performed on #101, just
          unprompted by a ticket.</p>

        <h4 class="step">c. Every discount request is priced from scratch</h4>
        <p class="says">On #103 accounting had to reach $50.00 itself. <code>get_price_and_margin</code>
          already scores any proposed price against <code>unit_cost</code> and returns
          <code>above_cost</code>. <b>Solvable today:</b> auto-score every
          <code>price_override</code> ticket on arrival, so a human opens it already knowing
          "$22.00 floor, $58.00 list, $50.00 leaves $28.00/unit". No new tools — just running
          the existing one before the ticket is read rather than after.</p>
      </div>
    </section>

    <!-- ============ 5. NOT SOLVABLE ============ -->
    <section class="block actual filled">
      <h3>5 · Three problems we could <i>not</i> solve, and what they would need</h3>
      <div class="body">
        <h4 class="step">a. Proving the rent notice is genuine</h4>
        <p class="says"><b>What happened:</b> facilities stated plainly that the notice
          "cannot be independently authenticated beyond the matching lease record". The
          database stores no email, no sender address, no headers, no attachment — only
          <code>tickets.notes</code> reading "Email: shop rent due in 2 days." A landlord
          impersonation would have passed every check we ran, because the only check available
          was that a name matched.</p>
        <p class="says"><b>Needed:</b> a <code>read_message(message_id)</code> MCP tool over
          the actual mailbox returning sender, headers and attachments, plus a
          <b>verification desk</b> that compares the claim against the lease, the payment
          history, and the sending domain. The agent was not failing here — it correctly
          reported a limit of the data, and no amount of prompting fixes a missing table.</p>

        <h4 class="step">b. Telling the customer when the tee actually arrives</h4>
        <p class="says"><b>What happened:</b> customer service refused to promise the
          2026-09-02 date, correctly, because <code>expected_delivery_date</code> is
          <i>derived</i> as <code>due_date + lead_days</code> — arithmetic on an invoice, not a
          commitment from Bulldog Print Co. Tauhid Zaman could be told "out of stock" but not
          "it arrives Tuesday". The schema has no <code>purchase_orders</code> table at all.</p>
        <p class="says"><b>Needed:</b> a <code>place_order</code> / <code>get_order_status</code>
          pair talking to the vendor's system, backed by a real purchase-order table, plus a
          <b>purchasing desk</b> that owns POs end to end. Only then does a promised date come
          from the party who can keep it.</p>

        <h4 class="step">c. Choosing which bill to pay when both cannot be paid</h4>
        <p class="says"><b>What happened:</b> accounting reached the <b>$160</b> figure on
          <i>two separate tickets</i> and escalated both times without ever proposing a
          sequence. That was the right call, but it is also the shop's central question and the
          agents could not answer it. The reason is structural: the database records
          <i>outflows</i> only — <code>invoices</code>, <code>leases</code>, <code>payments</code>
          — and has no sales, orders, or revenue table. Nothing in the data says money is
          coming in, so no agent can responsibly rank payments.</p>
        <p class="says"><b>Needed:</b> a <code>get_cash_forecast(days)</code> tool over
          projected inflows (which requires a sales table that does not exist), plus a
          <b>treasury desk</b> carrying an explicit written policy — rent before trade payables,
          or rank by late penalty and relationship risk. Without both the forecast and the
          policy, "which bill first" is not an agent question; it is the owner's.</p>

        <div class="notexpected">
          <div class="label">The common thread</div>
          <ul>
            <li>All three failures are <b>missing data</b>, not missing intelligence. The agents
              correctly identified every one of these limits themselves rather than inventing
              an answer — which is the behaviour the tools were built to force.</li>
            <li>Two of the three need a <b>new table</b> before a new tool makes sense: stored
              correspondence, and purchase orders. A tool over data that does not exist would
              just be a more confident guess.</li>
          </ul>
        </div>
      </div>
    </section>
"""


def main() -> None:
    html = PAGE.read_text(encoding="utf-8")
    m = re.search(
        r'(<div class="panel" role="tabpanel" id="panel-reflections".*?>)(.*?)(\n  </div><!-- /panels -->)',
        html, re.S,
    )
    if not m:
        raise SystemExit("reflections panel not found")
    html = html[: m.start(2)] + "\n" + REFLECTIONS + html[m.end(2) :]
    PAGE.write_text(html, encoding="utf-8")
    print(f"reflections filled — {len(html):,} chars")


if __name__ == "__main__":
    main()
