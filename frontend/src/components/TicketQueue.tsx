import type { Ticket } from "../lib/api";
import { disposition, ticketType } from "../lib/agents";

interface Props {
  tickets: Ticket[];
  selectedId: number | null;
  busyTicketId: number | null;
  onSelect: (id: number) => void;
}

/**
 * The queue rail.
 *
 * Open tickets sit at the top at full contrast; closed ones drop below a divider
 * and recede. The point is that the rail answers "what still needs me?" without
 * being read — the eye lands on the bright group.
 */
export function TicketQueue({ tickets, selectedId, busyTicketId, onSelect }: Props) {
  const open = tickets.filter((t) => t.is_open);
  const closed = tickets.filter((t) => !t.is_open);

  const card = (t: Ticket) => {
    const kind = ticketType(t.type);
    const chip = disposition(t.is_open ? "open" : t.status);
    const working = busyTicketId === t.ticket_id;
    return (
      <button
        key={t.ticket_id}
        className={`ticket${t.is_open ? "" : " closed"}`}
        style={{ ["--accent" as string]: kind.accent }}
        aria-pressed={selectedId === t.ticket_id}
        onClick={() => onSelect(t.ticket_id)}
      >
        <div className="num">#{t.ticket_id}</div>
        <div className="subject">{t.subject}</div>
        <div className="who">{t.requester}</div>
        <div className="foot">
          <span
            className="badge"
            style={{ background: chip.bg, color: chip.color }}
          >
            {working ? "Working…" : chip.label}
          </span>
          <span className="kind">{kind.label}</span>
        </div>
      </button>
    );
  };

  return (
    <section className="panel">
      <header>
        <h2>Queue</h2>
        <span className="count">
          {open.length} open · {closed.length} closed
        </span>
      </header>
      <div className="queue">
        {open.length === 0 && closed.length === 0 && (
          <div className="empty">
            <span className="big">Nothing in the queue</span>
            No tickets found.
          </div>
        )}
        {open.map(card)}
        {closed.length > 0 && (
          <>
            {open.length > 0 && <div className="queue-divider">Closed</div>}
            {closed.map(card)}
          </>
        )}
      </div>
    </section>
  );
}
