/**
 * The dashboard's single connection to the FastAPI backend.
 *
 * Nothing in the front end knows anything about the shop except what these calls
 * return. The backend in turn reads everything through the campus-customs MCP server,
 * so a number shown on screen traces back to a row in the database rather than to
 * anything invented along the way.
 */

const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* keep the status line */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

/* ----------------------------------------------------------------- types */

export type TicketState = "open" | "resolved";

export interface Ticket {
  ticket_id: number;
  type: string;
  requester: string;
  subject: string;
  status: string;
  is_open: boolean;
  state: TicketState;
  sku: string | null;
  size: string | null;
  qty: number | null;
  notes: string | null;
}

export interface TicketsResponse {
  as_of: string;
  count: number;
  open_count: number;
  resolved_count: number;
  tickets: Ticket[];
  source: string;
}

export interface Balance {
  account: string;
  balance: number;
  as_of: string;
  total_obligations: number;
  remaining_if_all_paid: number;
  can_cover_all: boolean;
  payments_recorded: number;
  source: string;
}

export type AgentName =
  | "boss"
  | "inventory"
  | "accounting"
  | "facilities"
  | "customer_service"
  | "shift"
  | "api";

export interface AgentEvent {
  ts: string;
  run_id: string;
  seq: number;
  event: string;
  agent: AgentName | null;
  ticket_id: number | null;
  tool?: string;
  is_write?: boolean;
  args?: Record<string, unknown>;
  said?: string;
  ok?: boolean;
  refusal_reason?: string | null;
  duration_ms?: number;
  delegated_to?: AgentName;
  recommendation?: string;
  facts_used?: string[];
  actions_taken?: string[];
  confidence?: string;
  disposition?: string;
  money_moved?: number;
  rule?: string;
}

export interface EventsResponse {
  total_records_in_trail: number;
  returned: number;
  runs_in_trail: string[];
  tools_used: string[];
  events: AgentEvent[];
  source: string;
}

export interface RunStatus {
  run_id: string;
  status: "running" | "done" | "error";
  ticket_id: number;
  ticket_subject: string;
  picked_randomly?: boolean;
  started_at?: string;
  finished_at?: string;
  error?: string;
  disposition?: string;
  decision?: string;
  specialists_consulted?: AgentName[];
  actions_taken?: string[];
  customer_message?: string | null;
  money_moved?: number;
  needs_human?: boolean;
  human_question?: string | null;
  tokens?: number;
  model_requests?: number;
}

export interface ApprovalResult {
  approved_by: string;
  action: string;
  executed: boolean;
  refused_reason: string | null;
  message: string;
  changes: Record<string, unknown>;
  balance_after: number | null;
  note: string;
}

/* ----------------------------------------------------------------- calls */

export const api = {
  tickets: () => json<TicketsResponse>("/api/tickets"),

  balance: () => json<Balance>("/api/balance"),

  events: (limit = 80, runId?: string) =>
    json<EventsResponse>(
      `/api/events?limit=${limit}${runId ? `&run_id=${encodeURIComponent(runId)}` : ""}`,
    ),

  startRun: (ticketId: number | null, approver: string) =>
    json<RunStatus & { ran: boolean; reason?: string }>("/api/run", {
      method: "POST",
      body: JSON.stringify({ ticket_id: ticketId, approver, wait: false }),
    }),

  runStatus: (runId: string) => json<RunStatus>(`/api/run/${runId}`),

  resolveTicket: (ticketId: number, note: string, resolvedBy: string, status = "resolved") =>
    json<{ ticket_id: number; resolved: boolean; message: string }>(
      `/api/tickets/${ticketId}/resolve`,
      { method: "POST", body: JSON.stringify({ status, note, resolved_by: resolvedBy }) },
    ),

  approvePayment: (
    kind: string,
    refId: number,
    amount: number,
    approvedBy: string,
    memo?: string,
  ) =>
    json<ApprovalResult>("/api/approve", {
      method: "POST",
      body: JSON.stringify({
        action: "payment",
        kind,
        ref_id: refId,
        amount,
        account: "checking",
        approved_by: approvedBy,
        memo,
      }),
    }),

  approvePurchase: (
    sku: string,
    size: string,
    qty: number,
    approvedBy: string,
    reason?: string,
  ) =>
    json<ApprovalResult>("/api/approve", {
      method: "POST",
      body: JSON.stringify({
        action: "purchase",
        sku,
        size,
        qty,
        approved_by: approvedBy,
        reason,
      }),
    }),

  reset: () =>
    json<{ reset: boolean; balance_now: number; open_tickets_now: number }>("/api/reset", {
      method: "POST",
    }),
};
