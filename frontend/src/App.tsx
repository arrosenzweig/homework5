import { useCallback, useEffect, useRef, useState } from "react";
import { api, type AgentEvent, type Balance, type RunStatus, type Ticket } from "./lib/api";
import { TicketQueue } from "./components/TicketQueue";
import { TicketDetail } from "./components/TicketDetail";
import { AgentRoster } from "./components/AgentRoster";
import { AgentStream } from "./components/AgentStream";
import { CashPanel } from "./components/CashPanel";
import { ApprovePanel } from "./components/ApprovePanel";

const APPROVER = "Alexandria Rosenzweig";
const POLL_MS = 1200;

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [balance, setBalance] = useState<Balance | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [run, setRun] = useState<RunStatus | null>(null);
  const [running, setRunning] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [offline, setOffline] = useState(false);
  const [toast, setToast] = useState<{ msg: string; kind: "ok" | "bad" } | null>(null);
  const [asOf, setAsOf] = useState("");

  const poll = useRef<number | null>(null);

  const flash = useCallback((msg: string, kind: "ok" | "bad" = "ok") => {
    setToast({ msg, kind });
    window.setTimeout(() => setToast(null), 4200);
  }, []);

  /* -------------------------------------------------------- loading */

  const loadCore = useCallback(async () => {
    try {
      const [t, b] = await Promise.all([api.tickets(), api.balance()]);
      setTickets(t.tickets);
      setAsOf(t.as_of);
      setBalance(b);
      setOffline(false);
      setSelected((cur) => cur ?? t.tickets.find((x) => x.is_open)?.ticket_id ?? t.tickets[0]?.ticket_id ?? null);
    } catch {
      setOffline(true);
    }
  }, []);

  useEffect(() => { void loadCore(); }, [loadCore]);

  /* ----------------------------------------------------- the run loop */

  // While a run is in flight the board polls two things: the run's own status and
  // the audit trail filtered to that run. The trail is what makes the desks visible
  // as they work rather than only once they finish.
  useEffect(() => {
    if (!running || !run?.run_id) return;

    const tick = async () => {
      try {
        const [status, ev] = await Promise.all([
          api.runStatus(run.run_id),
          api.events(120, run.run_id),
        ]);
        setEvents(ev.events);
        if (status.status !== "running") {
          setRun(status);
          setRunning(false);
          void loadCore();
          flash(
            status.status === "done"
              ? `#${status.ticket_id} → ${status.disposition}`
              : `Run failed: ${status.error}`,
            status.status === "done" ? "ok" : "bad",
          );
        }
      } catch {
        /* a dropped poll is not fatal; the next one will catch up */
      }
    };

    poll.current = window.setInterval(tick, POLL_MS);
    void tick();
    return () => { if (poll.current) window.clearInterval(poll.current); };
  }, [running, run?.run_id, loadCore, flash]);

  /* ---------------------------------------------------------- actions */

  async function dispatch() {
    if (selected == null) return;
    setEvents([]);
    setRun(null);
    try {
      const started = await api.startRun(selected, APPROVER);
      if (!started.ran) { flash(started.reason ?? "Nothing to run.", "bad"); return; }
      setRun(started);
      setRunning(true);
    } catch (e) {
      flash(e instanceof Error ? e.message : String(e), "bad");
    }
  }

  async function resolve(note: string) {
    if (selected == null) return;
    setResolving(true);
    try {
      await api.resolveTicket(selected, note, APPROVER);
      await loadCore();
      flash(`Ticket #${selected} closed.`);
    } catch (e) {
      flash(e instanceof Error ? e.message : String(e), "bad");
    } finally {
      setResolving(false);
    }
  }

  async function reset() {
    try {
      const r = await api.reset();
      setEvents([]); setRun(null); setSelected(null);
      await loadCore();
      flash(`Reset — ${r.open_tickets_now} open tickets, balance restored.`);
    } catch (e) {
      flash(e instanceof Error ? e.message : String(e), "bad");
    }
  }

  const ticket = tickets.find((t) => t.ticket_id === selected) ?? null;
  const openCount = tickets.filter((t) => t.is_open).length;

  /* ------------------------------------------------------------ view */

  return (
    <div className="shell">
      <div className="topbar">
        <div className="brand">
          <span className="mark">Y</span>
          <div>
            <h1>Campus Customs — Desk Board</h1>
            <div className="tag">Agent operations · all figures read over MCP</div>
          </div>
        </div>
        <div className="spacer" />
        {asOf && <span className="chip">Shift <b>{asOf}</b></span>}
        <span className="chip">
          <b>{openCount}</b> open
        </span>
        {running && <span className="chip live">Team working</span>}
        <button className="btn ghost sm" onClick={reset} disabled={running}>
          Reset day
        </button>
      </div>

      {offline ? (
        <div className="offline">
          <b>Cannot reach the backend at http://localhost:8000.</b>
          <br />
          Start it from the <code>backend/</code> folder with{" "}
          <code>uvicorn main:app --reload --port 8000</code>, then reload this page.
        </div>
      ) : (
        <div className="board">
          <div className="column">
            <TicketQueue
              tickets={tickets}
              selectedId={selected}
              busyTicketId={running ? (run?.ticket_id ?? null) : null}
              onSelect={(id) => { setSelected(id); if (!running) { setEvents([]); setRun(null); } }}
            />
          </div>

          <div className="column">
            <TicketDetail
              ticket={ticket}
              run={run}
              running={running}
              onDispatch={dispatch}
              onResolve={resolve}
              resolving={resolving}
            />
            <AgentRoster events={events} running={running} />
            <AgentStream events={events} running={running} />
          </div>

          <div className="column money">
            <CashPanel balance={balance} />
            <ApprovePanel
              approver={APPROVER}
              prefill={
                ticket?.sku
                  ? { sku: ticket.sku, size: ticket.size ?? "", qty: ticket.qty ?? 1 }
                  : null
              }
              onDone={loadCore}
            />
          </div>
        </div>
      )}

      {toast && <div className={`toast ${toast.kind}`}>{toast.msg}</div>}
    </div>
  );
}
