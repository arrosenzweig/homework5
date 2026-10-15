import type { Balance } from "../lib/api";

const money = (n: number | null | undefined) =>
  n == null ? "—" : `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/**
 * The money panel.
 *
 * A bare balance is misleading when two bills are already drawing on it, so the
 * number is shown on top of a meter that splits the account into what is already
 * committed and what is genuinely free. A thin remainder is called out in amber
 * rather than left for the reader to compute.
 */
export function CashPanel({ balance }: { balance: Balance | null }) {
  if (!balance) {
    return (
      <section className="panel cash">
        <header><h2>Checking</h2></header>
        <div className="body"><div className="amount">—</div></div>
      </section>
    );
  }

  const owed = balance.total_obligations ?? 0;
  const free = Math.max(0, balance.balance - owed);
  const committedPct = balance.balance > 0 ? Math.min(100, (owed / balance.balance) * 100) : 0;
  const thin = free < 500;

  return (
    <section className="panel cash">
      <header>
        <h2>Checking</h2>
        <span className="count">{balance.payments_recorded} paid</span>
      </header>
      <div className="body">
        <div className="amount">{money(balance.balance)}</div>
        <div className="asof">as of {balance.as_of} · from cash_accounts</div>

        <div className="meter">
          <div className="track">
            <div
              className="seg"
              style={{ width: `${committedPct}%`, background: "#c9a227" }}
              title="Already owed"
            />
            <div
              className="seg"
              style={{ width: `${100 - committedPct}%`, background: "#2f9e6b" }}
              title="Free after obligations"
            />
          </div>
          <div className="legend">
            <span className="key">
              <span className="swatch" style={{ background: "#c9a227" }} />
              owed <b>{money(owed)}</b>
            </span>
            <span className="key">
              <span className="swatch" style={{ background: "#2f9e6b" }} />
              free <b>{money(free)}</b>
            </span>
          </div>
        </div>

        <div className="ledger">
          <div className="row">
            <span>Balance</span><b>{money(balance.balance)}</b>
          </div>
          <div className="row">
            <span>Obligations</span><b>−{money(owed)}</b>
          </div>
          <div className={`row total${thin ? " thin" : ""}`}>
            <span>If all paid</span><b>{money(balance.remaining_if_all_paid)}</b>
          </div>
        </div>

        {thin && (
          <div className="note warn">
            Paying everything would leave {money(balance.remaining_if_all_paid)}. The team
            is expected to escalate rather than spend down to this.
          </div>
        )}
        {!balance.can_cover_all && (
          <div className="note bad">
            Obligations exceed the balance. Not everything can be paid.
          </div>
        )}
      </div>
    </section>
  );
}
