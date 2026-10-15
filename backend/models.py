"""Data types for the Campus Customs agent team.

These are the shapes the agents speak in. Specialists return a `SpecialistReport`, the
boss returns a `TicketResolution`, and a whole shift is a `ShiftReport`.

Why typed outputs rather than free text: a specialist that must fill `facts_used` cannot
quietly assert a number it never looked up, and a boss that must fill `actions_taken`
cannot claim a ticket is handled without naming what it did. The schema is itself a
guardrail.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Specialist(str, Enum):
    """The four desks the boss can delegate to."""

    INVENTORY = "inventory"
    ACCOUNTING = "accounting"
    FACILITIES = "facilities"
    CUSTOMER_SERVICE = "customer_service"


class Confidence(str, Enum):
    """How firmly a specialist stands behind its finding."""

    HIGH = "high"       # every claim came from a tool result
    MEDIUM = "medium"   # tool-backed, but needs a judgement call
    LOW = "low"         # the data did not settle the question


class Disposition(str, Enum):
    """How the boss closed a ticket."""

    RESOLVED = "resolved"
    DECLINED = "declined"
    ESCALATED = "escalated"
    BLOCKED = "blocked"


# --------------------------------------------------------------------------- #
# Shared run context
# --------------------------------------------------------------------------- #


class TeamDeps(BaseModel):
    """Dependencies handed to every agent in the team.

    `approver` is the human whose name goes on any payment — the team never invents an
    approver. `audit_run_id` ties every record this shift writes to one run.
    """

    model_config = {"arbitrary_types_allowed": True}

    approver: str = Field(description="Human authorising payments this shift.")
    audit_run_id: str
    shift_date: str | None = Field(
        default=None, description="desk.date_today, filled in once the queue is read."
    )
    max_delegations_per_ticket: int = Field(
        default=4, description="Token guardrail: delegation calls allowed per ticket."
    )


# --------------------------------------------------------------------------- #
# Specialist output
# --------------------------------------------------------------------------- #


class SpecialistReport(BaseModel):
    """What one desk reports back to the boss."""

    desk: Specialist
    finding: str = Field(
        description="What is true, in one or two sentences, stated from tool results only."
    )
    facts_used: list[str] = Field(
        default_factory=list,
        description=(
            "Each concrete figure relied on and the tool it came from, e.g. "
            "'check_stock: CC-TEE-WHITE size S qty=0'. A claim with no entry here is "
            "unsupported and must not be made."
        ),
    )
    recommendation: str = Field(description="The action this desk advises, stated plainly.")
    actions_taken: list[str] = Field(
        default_factory=list,
        description="Writes actually performed, with the tool name. Empty if read-only.",
    )
    blocked_by: str | None = Field(
        default=None, description="What prevented action, if anything did."
    )
    needs_human: bool = Field(
        default=False, description="True when a human must decide before acting."
    )
    confidence: Confidence = Confidence.HIGH


# --------------------------------------------------------------------------- #
# Boss output
# --------------------------------------------------------------------------- #


class TicketResolution(BaseModel):
    """The boss's decision on one ticket."""

    ticket_id: int
    disposition: Disposition
    decision: str = Field(description="What was decided and the reason, in plain language.")
    specialists_consulted: list[Specialist] = Field(default_factory=list)
    actions_taken: list[str] = Field(
        default_factory=list, description="Every write performed for this ticket."
    )
    customer_message: str | None = Field(
        default=None,
        description="The reply to send the requester. None when there is nobody to answer.",
    )
    money_moved: float = Field(
        default=0.0, description="Total paid out on this ticket. 0.0 when nothing was paid."
    )
    needs_human: bool = False
    human_question: str | None = Field(
        default=None, description="The single question for a human, when one is needed."
    )


class ShiftReport(BaseModel):
    """The whole run: one resolution per ticket, plus what it cost."""

    run_id: str
    shift_date: str
    approver: str
    tickets_seen: int
    tickets_handled: int
    resolutions: list[TicketResolution] = Field(default_factory=list)
    total_money_moved: float = 0.0
    escalations: list[str] = Field(default_factory=list)
    stop_reason: str = Field(
        default="completed",
        description="completed, limit_reached, or error — how the loop terminated.",
    )
    total_requests: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    notes: list[str] = Field(default_factory=list)
