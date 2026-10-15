import type { AgentEvent, AgentName } from "../lib/api";
import { AGENTS, SPECIALISTS } from "../lib/agents";

/**
 * The roster: one lane per agent, showing what that desk is doing right now.
 *
 * This is the answer to "who is working and on what" at a glance. A lane is idle,
 * active (accented border, pulsing rail), or done. The boss gets a full-width lane
 * above the four specialists because it is the only one that decides — the others
 * advise it.
 */

interface Props {
  events: AgentEvent[];
  running: boolean;
}

interface LaneState {
  active: boolean;
  touched: boolean;
  doing: string;
  tools: { name: string; write: boolean; refused: boolean }[];
}

function laneStates(events: AgentEvent[], running: boolean): Record<string, LaneState> {
  const out: Record<string, LaneState> = {};
  for (const key of ["boss", ...SPECIALISTS]) {
    out[key] = { active: false, touched: false, doing: "", tools: [] };
  }

  // The last agent to produce an event is the one currently holding the floor.
  let lastActor: string | null = null;

  for (const e of events) {
    const actor = e.event === "delegation" ? e.delegated_to : e.agent;
    if (!actor || !(actor in out)) continue;
    const lane = out[actor];
    lane.touched = true;

    if (e.event === "delegation" && e.delegated_to) {
      out[e.delegated_to].doing = e.said ?? "";
      lastActor = e.delegated_to;
    } else if (e.event === "delegation_result") {
      lane.doing = e.said ?? lane.doing;
      lane.active = false;
    } else if (e.event === "tool_call" && e.tool) {
      lane.tools.push({
        name: e.tool,
        write: Boolean(e.is_write),
        refused: e.ok === false,
      });
      lane.doing = e.said ?? lane.doing;
      lastActor = actor;
    } else if (e.said) {
      lane.doing = e.said;
      lastActor = actor;
    }
  }

  if (running && lastActor && out[lastActor]) out[lastActor].active = true;
  return out;
}

export function AgentRoster({ events, running }: Props) {
  const states = laneStates(events, running);

  const lane = (key: AgentName) => {
    const id = AGENTS[key];
    const st = states[key];
    const status = st.active ? "Working" : st.touched ? "Reported" : "Idle";
    const cls = st.active ? "active" : st.touched ? "" : "idle";

    return (
      <div
        key={key}
        className={`lane ${cls}${id.isLead ? " lead" : ""}`}
        style={{
          ["--accent" as string]: id.color,
          ["--accent-tint" as string]: id.tint,
        }}
      >
        <div className="top">
          <span
            className="glyph"
            style={{
              background: id.isLead ? id.color : id.tint,
              color: id.isLead ? "#fff" : id.color,
              border: `1px solid ${id.border}`,
            }}
          >
            {id.glyph}
          </span>
          <span className="name" style={{ color: id.color }}>{id.label}</span>
          <span
            className="status"
            style={{
              background: st.active ? id.tint : "transparent",
              color: st.active ? id.color : "var(--faint)",
            }}
          >
            {status}
          </span>
        </div>

        {st.doing ? (
          <div className="doing">{st.doing}</div>
        ) : (
          <div className="owns">{id.owns}</div>
        )}

        {st.tools.length > 0 && (
          <div className="calls">
            {st.tools.slice(-4).map((t, i) => (
              <span
                key={i}
                className={`toolchip ${t.refused ? "refused" : t.write ? "write" : "read"}`}
              >
                {t.name}
              </span>
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <section className="panel">
      <header>
        <h2>The desks</h2>
        <span className="count">
          {Object.values(states).filter((s) => s.touched).length} of 5 engaged
        </span>
      </header>
      <div className="roster">
        {lane("boss")}
        {SPECIALISTS.map((s) => lane(s))}
      </div>
    </section>
  );
}
