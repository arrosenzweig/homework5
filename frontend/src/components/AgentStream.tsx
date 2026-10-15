import { useEffect, useRef } from "react";
import type { AgentEvent } from "../lib/api";
import { agentOf, describeEvent } from "../lib/agents";

/**
 * The transcript: every step, in order, as it happened.
 *
 * The roster says who is working; this says what was actually said and done. Each
 * row is keyed to its agent's colour so a reader can follow one desk down the
 * column, and writes and refusals are pulled out visually because those are the
 * rows that changed something.
 */
export function AgentStream({ events, running }: { events: AgentEvent[]; running: boolean }) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (running) endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [events.length, running]);

  const shown = events.filter(
    (e) => !["usage", "run_start", "ticket_start"].includes(e.event),
  );

  return (
    <section className="panel">
      <header>
        <h2>Transcript</h2>
        <span className="count">{shown.length} steps</span>
      </header>

      {shown.length === 0 ? (
        <div className="empty">
          <span className="big">No activity yet</span>
          Pick a ticket and send the team in.
        </div>
      ) : (
        <div className="stream">
          {shown.map((e, i) => {
            // A delegation is the boss speaking *to* a desk, so colour it by the
            // desk being asked — that is the thread a reader is following.
            const subject = e.event === "delegation" ? e.delegated_to : e.agent;
            const id = agentOf(subject);
            const refused = e.ok === false;
            const write = Boolean(e.is_write);

            return (
              <div
                key={`${e.run_id}-${e.seq}-${i}`}
                className={`entry${write ? " is-write" : ""}${refused ? " is-refused" : ""}`}
              >
                <div className="rail">
                  <span
                    className="dot"
                    style={{
                      background: id.isLead ? id.color : id.tint,
                      color: id.isLead ? "#fff" : id.color,
                      border: `1px solid ${id.border}`,
                    }}
                  >
                    {id.glyph}
                  </span>
                  {i < shown.length - 1 && <span className="line" />}
                </div>

                <div>
                  <div className="head">
                    <span className="actor" style={{ color: id.color }}>
                      {e.event === "delegation" ? `Boss → ${id.label}` : id.label}
                    </span>
                    <span className="verb">{describeEvent(e.event)}</span>
                    {e.ticket_id && <span className="verb">· #{e.ticket_id}</span>}
                    {e.duration_ms != null && (
                      <span className="time">{e.duration_ms}ms</span>
                    )}
                  </div>

                  {e.said && <div className="said">{e.said}</div>}

                  {(e.tool || refused || e.actions_taken?.length) && (
                    <div className="extras">
                      {e.tool && (
                        <span
                          className={`toolchip ${refused ? "refused" : write ? "write" : "read"}`}
                        >
                          {e.tool}
                          {write && !refused ? " · write" : ""}
                        </span>
                      )}
                      {refused && e.refusal_reason && (
                        <span className="toolchip refused">{e.refusal_reason}</span>
                      )}
                      {e.actions_taken?.map((a, k) => (
                        <span key={k} className="toolchip write">{a}</span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
          <div ref={endRef} />
        </div>
      )}
    </section>
  );
}
