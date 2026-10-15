import { useState } from "react";
import { api, type ApprovalResult } from "../lib/api";

/**
 * Manual approval.
 *
 * The team escalates rather than spending on its own authority, so this is where a
 * human finishes the job. The panel deliberately keeps the backend's refusal text
 * verbatim: approving something does not make it safe, and a refused approval is
 * the most important thing this panel can show.
 */
export function ApprovePanel({
  approver,
  prefill,
  onDone,
}: {
  approver: string;
  prefill: { sku?: string; size?: string; qty?: number } | null;
  onDone: () => void;
}) {
  const [mode, setMode] = useState<"payment" | "purchase">("payment");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ApprovalResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [kind, setKind] = useState("invoice");
  const [refId, setRefId] = useState("501");
  const [amount, setAmount] = useState("840.00");

  const [sku, setSku] = useState(prefill?.sku ?? "CC-TEE-WHITE");
  const [size, setSize] = useState(prefill?.size ?? "S");
  const [qty, setQty] = useState(String(prefill?.qty ?? 12));
  const [reason, setReason] = useState("Reprint delivered");

  async function submit() {
    setBusy(true);
    setResult(null);
    setError(null);
    try {
      const r =
        mode === "payment"
          ? await api.approvePayment(kind, Number(refId), Number(amount), approver,
              "Approved from the desk board")
          : await api.approvePurchase(sku, size, Number(qty), approver, reason);
      setResult(r);
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel approve">
      <header>
        <h2>Approve</h2>
        <span className="count">as {approver.split(" ")[0]}</span>
      </header>

      <div className="tabs" role="tablist">
        <button
          role="tab"
          aria-selected={mode === "payment"}
          onClick={() => { setMode("payment"); setResult(null); setError(null); }}
        >
          Payment
        </button>
        <button
          role="tab"
          aria-selected={mode === "purchase"}
          onClick={() => { setMode("purchase"); setResult(null); setError(null); }}
        >
          Purchase
        </button>
      </div>

      <div className="form">
        {mode === "payment" ? (
          <>
            <div className="pair">
              <div className="field">
                <label htmlFor="ap-kind">Kind</label>
                <select id="ap-kind" value={kind} onChange={(e) => setKind(e.target.value)}>
                  <option value="invoice">Invoice</option>
                  <option value="rent">Rent</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="ap-ref">Reference</label>
                <input id="ap-ref" value={refId} onChange={(e) => setRefId(e.target.value)} />
              </div>
            </div>
            <div className="field">
              <label htmlFor="ap-amt">Amount</label>
              <input id="ap-amt" value={amount} onChange={(e) => setAmount(e.target.value)} />
            </div>
          </>
        ) : (
          <>
            <div className="pair">
              <div className="field">
                <label htmlFor="ap-sku">SKU</label>
                <input id="ap-sku" value={sku} onChange={(e) => setSku(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="ap-size">Size</label>
                <input id="ap-size" value={size} onChange={(e) => setSize(e.target.value)} />
              </div>
            </div>
            <div className="pair">
              <div className="field">
                <label htmlFor="ap-qty">Units in</label>
                <input id="ap-qty" value={qty} onChange={(e) => setQty(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="ap-why">Reason</label>
                <input id="ap-why" value={reason} onChange={(e) => setReason(e.target.value)} />
              </div>
            </div>
          </>
        )}

        <button className="btn ok" onClick={submit} disabled={busy} style={{ width: "100%" }}>
          {busy && <span className="spinner" />}
          {busy ? "Submitting…" : mode === "payment" ? "Approve payment" : "Approve purchase"}
        </button>

        {error && <div className="note bad">{error}</div>}

        {result && (
          <div className={`note ${result.executed ? "ok" : "bad"}`}>
            <b>{result.executed ? "Done. " : "Refused. "}</b>
            {result.message}
          </div>
        )}

        {!result && !error && (
          <div className="note info">
            Approval does not bypass the safety checks. A payment that would overdraw the
            account, repeat an earlier one, or miss the amount on file is still refused.
          </div>
        )}
      </div>
    </section>
  );
}
