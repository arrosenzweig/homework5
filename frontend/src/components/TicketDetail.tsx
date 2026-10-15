import { useState } from "react";
import type { RunStatus, Ticket } from "../lib/api";
import { AGENTS, disposition, ticketType } from "../lib/agents";

const money = (n?: number | null) =>
  n == null ? "$0.00" : `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

interface Props {
  ticket: Ticket | null;
  run: RunStatus | null;
  running: boolean;
  onDispatch: () => void;
  onResolve: (note: string) => void;
  resolving: boolean;
}

/**
 * The centre column: what this ticket is, the controls for it, and — once the team
 * has run — a short summary of what the agents actually did.
 */
export function TicketDetail({
  ticket, run, running, onDispatch, onResolve, resolving,
}: Props) {
  const [note, setNote] = useState("");
  const [closing, setClosing] = useState(false);

  if (!ticket) {
    return (
      <section className="panel detail">
        <div className="empty">
          <span className="big">No ticket selected</span>
          Choose one from the queue to see it here.
        </div>
      </section>
    );
  }

  const kind = ticketType(ticket.type);
  const chip = disposition(ticket.is_open ? "open" : ticket.status);
  const summary = run && run.status === "done" && run.ticket_id === ticket.ticket_id ? run : null;
  const dispo = summary ? disposition(summary.disposition ?? "") : null;

  return (
    <section className="panel detail">
      <div className="head">
        <div className="eyebrow">
          <span className="badge" style={{ background: chip.bg, color: chip.color }}>
            {chip.label}
          </span>
          <span className="kind" style={{ color: kind.accent, fontWeight: 650 }}>
            {kind.label}
          </span>
          <span className="kind">#{ticket.ticket_id}</span>
        </div>
        <h2>{ticket.subject}</h2>
        <div className="meta">from {ticket.requester}</div>

        {ticket.notes && <p className="quote">{ticket.notes}</p>}

        <div className="facts">
          {ticket.sku && <span className="fact">{ticket.sku}</span>}
          {ticket.size && <span className="fact">size {ticket.size}</span>}
          {ticket.qty != null && <span className="fact">qty {ticket.qty}</span>}
        </div>
      </div>

      <div className="actionbar">
        <button className="btn" onClick={onDispatch} disabled={running || !ticket.is_open}>
          {running && <span className="spinner" />}
          {running ? "Team working…" : "Send the team in"}
        </button>

        {ticket.is_open && !closing && (
          <button className="btn ghost" onClick={() => setClosing(true)} disabled={running}>
            Mark resolved
          </button>
        )}
        {!ticket.is_open && (
          <span className="kind">
            Closed as <b style={{ color: chip.color }}>{ticket.status}</b>
          </span>
        )}
      </div>

      {closing && (
        <div className="actionbar" style={{ background: "var(--warn-bg)", borderColor: "#eadfba" }}>
          <input
            className="field"
            style={{ flex: 1, minWidth: 220, padding: "7px 10px", border: "1px solid var(--line)",
                     borderRadius: "var(--r-sm)", fontSize: 13.5 }}
            placeholder="Why is this resolved? (recorded on the ticket)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            autoFocus
          />
          <button
            className="btn ok sm"
            disabled={!note.trim() || resolving}
            onClick={() => { onResolve(note.trim()); setNote(""); setClosing(false); }}
          >
            {resolving ? "Closing…" : "Confirm"}
          </button>
          <button className="btn quiet sm" onClick={() => { setClosing(false); setNote(""); }}>
            Cancel
          </button>
        </div>
      )}

      {summary && (
        <div className="summary">
          <div
            className="bar"
            style={{ background: dispo?.bg, color: dispo?.color }}
          >
            <span>{dispo?.label}</span>
            <span style={{ marginLeft: "auto", fontWeight: 600, letterSpacing: 0 }}>
              {money(summary.money_moved)} moved
            </span>
          </div>

          <div className="inner">
            <div className="decision">{summary.decision}</div>

            {summary.specialists_consulted && summary.specialists_consulted.length > 0 && (
              <>
                <h4>Desks consulted</h4>
                <div className="facts">
                  {summary.specialists_consulted.map((s) => {
                    const id = AGENTS[s];
                    return (
                      <span
                        key={s}
                        className="fact"
                        style={{ background: id.tint, color: id.color, borderColor: id.border }}
                      >
                        {id.glyph} {id.label}
                      </span>
                    );
                  })}
                </div>
              </>
            )}

            {summary.actions_taken && summary.actions_taken.length > 0 && (
              <>
                <h4>What they did</h4>
                <ul>
                  {summary.actions_taken.map((a, i) => <li key={i}>{a}</li>)}
                </ul>
              </>
            )}

            {summary.needs_human && summary.human_question && (
              <>
                <h4>Waiting on you</h4>
                <div className="ask">{summary.human_question}</div>
              </>
            )}

            {summary.customer_message && (
              <>
                <h4>Drafted reply</h4>
                <div className="msg">{summary.customer_message}</div>
              </>
            )}

            <div className="stats">
              <span>tokens <b>{summary.tokens?.toLocaleString()}</b></span>
              <span>model calls <b>{summary.model_requests}</b></span>
              <span>run <b>{summary.run_id.replace("run-", "")}</b></span>
            </div>
          </div>
        </div>
      )}

      {run?.status === "error" && (
        <div className="summary">
          <div className="bar" style={{ background: "var(--bad-bg)", color: "var(--bad)" }}>
            Run failed
          </div>
          <div className="inner"><div className="decision">{run.error}</div></div>
        </div>
      )}
    </section>
  );
}
