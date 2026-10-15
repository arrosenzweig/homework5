/**
 * Visual identity for each agent.
 *
 * The five agents do genuinely different jobs, so they are given genuinely different
 * appearances: a colour, a glyph, and a one-line description of what that desk owns.
 * Once a reader learns "amber means stock" they can scan the activity stream without
 * reading a single name — which matters when forty events arrive in thirty seconds.
 *
 * The boss is deliberately the odd one out: it is the only agent rendered in solid
 * navy with a filled badge, because it is the only one that decides. The four
 * specialists advise, and are rendered as lighter tinted chips.
 */

import type { AgentName } from "./api";

export interface AgentIdentity {
  key: AgentName;
  label: string;
  owns: string;
  glyph: string;
  /** Hue drives the chip, the lane accent, and the stream rail. */
  color: string;
  tint: string;
  border: string;
  /** The boss is rendered as a decision-maker, not an adviser. */
  isLead?: boolean;
}

export const AGENTS: Record<AgentName, AgentIdentity> = {
  boss: {
    key: "boss",
    label: "Shift manager",
    owns: "Reads the queue, routes the work, makes the call",
    glyph: "★",
    color: "#00356b",
    tint: "#e6edf6",
    border: "#b9cbe2",
    isLead: true,
  },
  inventory: {
    key: "inventory",
    label: "Inventory",
    owns: "Stock on hand, shortfalls, restock timing",
    glyph: "▦",
    color: "#a8620a",
    tint: "#fdf1e3",
    border: "#f0d6b4",
  },
  accounting: {
    key: "accounting",
    label: "Accounting",
    owns: "Cash, bills, margins — the only desk that can pay",
    glyph: "$",
    color: "#13754a",
    tint: "#e9f6ef",
    border: "#bfe3d0",
  },
  facilities: {
    key: "facilities",
    label: "Facilities",
    owns: "The lease, rent, landlord claims",
    glyph: "⌂",
    color: "#5b3fa8",
    tint: "#f1ecfb",
    border: "#d8cbf2",
  },
  customer_service: {
    key: "customer_service",
    label: "Customer service",
    owns: "What the requester is actually told",
    glyph: "✉",
    color: "#0d6b78",
    tint: "#e6f5f7",
    border: "#b8dfe4",
  },
  shift: {
    key: "shift",
    label: "Shift",
    owns: "Run bookkeeping",
    glyph: "◷",
    color: "#5b6673",
    tint: "#eef1f5",
    border: "#d8dee6",
  },
  api: {
    key: "api",
    label: "Desk",
    owns: "Human actions taken at the dashboard",
    glyph: "◆",
    color: "#8a6d1f",
    tint: "#fdf8e9",
    border: "#eadfba",
  },
};

export const SPECIALISTS: AgentName[] = [
  "inventory",
  "accounting",
  "facilities",
  "customer_service",
];

export function agentOf(name?: string | null): AgentIdentity {
  if (name && name in AGENTS) return AGENTS[name as AgentName];
  return AGENTS.shift;
}

/**
 * Plain-language description of what an event actually is.
 * The raw event names are accurate but unreadable at a glance.
 */
export function describeEvent(event: string): string {
  switch (event) {
    case "run_start":
      return "dispatched";
    case "run_end":
      return "shift closed";
    case "ticket_start":
      return "picked up";
    case "ticket_end":
      return "decided";
    case "delegation":
      return "asked";
    case "delegation_result":
      return "reported back";
    case "tool_call":
      return "looked up";
    case "guardrail":
      return "blocked";
    case "usage":
      return "cost";
    case "human_approval":
      return "you approved";
    case "human_approval_result":
      return "approval result";
    case "manual_resolution":
      return "you closed";
    case "database_reset":
      return "reset";
    case "error":
      return "failed";
    default:
      return event.replace(/_/g, " ");
  }
}

/** Ticket type → a human label and an accent. */
export const TICKET_TYPES: Record<string, { label: string; accent: string }> = {
  customer_order: { label: "Customer order", accent: "#0d6b78" },
  rent_notice: { label: "Rent notice", accent: "#5b3fa8" },
  price_override: { label: "Discount request", accent: "#a8620a" },
};

export function ticketType(type: string) {
  return TICKET_TYPES[type] ?? { label: type.replace(/_/g, " "), accent: "#5b6673" };
}

/** Disposition → how a closed ticket should read. */
export const DISPOSITIONS: Record<string, { label: string; color: string; bg: string }> = {
  resolved: { label: "Resolved", color: "#13754a", bg: "#e9f6ef" },
  declined: { label: "Declined", color: "#a33a3a", bg: "#fdf0f0" },
  escalated: { label: "Needs you", color: "#8a6d1f", bg: "#fdf8e9" },
  blocked: { label: "Blocked", color: "#5b6673", bg: "#eef1f5" },
  open: { label: "Open", color: "#00356b", bg: "#e6edf6" },
};

export function disposition(status: string) {
  return (
    DISPOSITIONS[status?.toLowerCase()] ?? {
      label: status,
      color: "#5b6673",
      bg: "#eef1f5",
    }
  );
}
