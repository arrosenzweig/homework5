"""The Campus Customs agent team.

Five Pydantic AI agents:

    boss (shift manager)
      ├── inventory          stock, shortfalls, restock timing
      ├── accounting         cash, invoices, margins, payments
      ├── facilities         the lease, rent, landlord claims
      └── customer_service   what the requester is actually told

The boss does not do specialist work. It reads a ticket, delegates to the desks that
own part of the question, and decides. Delegation is implemented as agent tools on the
boss: each one runs a specialist agent and returns its structured report.

Two details make that delegation safe and affordable:

* **Shared usage.** Every delegated run is passed `usage=ctx.usage`, so the whole
  ticket — boss plus every desk it consulted — draws on one token budget and one set of
  `UsageLimits`. Without this a four-desk ticket could quietly cost five times its cap.
* **Least privilege.** Each desk gets an MCP toolset filtered to the tools it needs
  (see `mcp_client.DESK_TOOLS`). Customer service cannot move money because it cannot
  see `record_payment`, not merely because its prompt says not to.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

from mcp_client import build_toolset
from models import Specialist, SpecialistReport, TeamDeps, TicketResolution

HW5_ROOT = Path(__file__).resolve().parent.parent
PROMPTS = Path(__file__).resolve().parent / "prompts"

# PORTKEY_API_KEY lives in the repository root .env, one level above HW 5.
load_dotenv(HW5_ROOT.parent / ".env")
load_dotenv(HW5_ROOT / ".env", override=False)

PORTKEY_BASE_URL = os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1")
PORTKEY_API_KEY = os.getenv("PORTKEY_API_KEY")
MODEL_NAME = os.getenv("SHOP_MODEL", "gpt-5.6-luna")

# ---------------------------------------------------------------------------- #
# Token guardrails
#
# These are ceilings, not targets. They exist so a confused agent cannot loop
# indefinitely at the shop's expense. The per-ticket budget covers the boss and every
# desk it delegates to, because they share one usage object.
# ---------------------------------------------------------------------------- #

TICKET_LIMITS = UsageLimits(
    request_limit=26,          # model round trips for one ticket, all desks included
    tool_calls_limit=36,       # MCP calls for one ticket
    total_tokens_limit=220_000,
)
SPECIALIST_RETRIES = 2


def load_prompt(name: str) -> str:
    """Load a desk's prompt, prefixed with the rules every agent shares."""
    shared = (PROMPTS / "_shared.md").read_text(encoding="utf-8")
    own = (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
    return f"{shared}\n\n---\n\n{own}"


def build_model() -> OpenAIChatModel:
    """Point Pydantic AI at Portkey.

    Portkey is OpenAI-compatible, so the OpenAI model class works unchanged; only the
    base URL and the auth header differ. The key is sent as `x-portkey-api-key`.
    """
    if not PORTKEY_API_KEY:
        raise RuntimeError(
            "PORTKEY_API_KEY is not set. Add it to the repository root .env file."
        )
    client = AsyncOpenAI(
        base_url=PORTKEY_BASE_URL,
        api_key=PORTKEY_API_KEY,
        default_headers={"x-portkey-api-key": PORTKEY_API_KEY},
    )
    return OpenAIChatModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


# ---------------------------------------------------------------------------- #
# Team assembly
# ---------------------------------------------------------------------------- #


class ShopTeam:
    """The five agents, wired together and sharing one audit trail."""

    def __init__(self, audit):
        self.audit = audit
        self.model = build_model()
        self._delegations: dict[int, int] = {}  # ticket_id -> delegation count

        self.inventory = self._specialist("inventory")
        self.accounting = self._specialist("accounting")
        self.facilities = self._specialist("facilities")
        self.customer_service = self._specialist("customer_service")

        self.boss = Agent(
            self.model,
            name="boss",
            deps_type=TeamDeps,
            output_type=TicketResolution,
            instructions=load_prompt("boss"),
            toolsets=[build_toolset("boss", audit)],
            retries=SPECIALIST_RETRIES,
        )
        self._register_delegation_tools()

    # -- specialists ------------------------------------------------------- #

    def _specialist(self, desk: str) -> Agent:
        return Agent(
            self.model,
            name=desk,
            deps_type=TeamDeps,
            output_type=SpecialistReport,
            instructions=load_prompt(desk),
            toolsets=[build_toolset(desk, self.audit)],
            retries=SPECIALIST_RETRIES,
        )

    async def _consult(
        self, desk: str, agent: Agent, ctx: RunContext[TeamDeps], question: str
    ) -> SpecialistReport:
        """Run a specialist inside the boss's run, sharing its token budget."""
        ticket_id = self._current_ticket
        used = self._delegations.get(ticket_id or 0, 0)
        if used >= ctx.deps.max_delegations_per_ticket:
            self.audit.guardrail(
                agent="boss", rule="max_delegations_per_ticket",
                detail=f"Refused a {used + 1}th delegation to {desk}; cap is "
                       f"{ctx.deps.max_delegations_per_ticket}.",
                ticket_id=ticket_id,
            )
            return SpecialistReport(
                desk=Specialist(desk),
                finding="Delegation budget for this ticket is exhausted.",
                recommendation=(
                    "Decide with the reports already gathered, or escalate to a human."
                ),
                confidence="low",
                needs_human=True,
                blocked_by="delegation cap reached",
            )
        self._delegations[ticket_id or 0] = used + 1

        self.audit.delegation(frm="boss", to=desk, question=question, ticket_id=ticket_id)
        result = await agent.run(
            question,
            deps=ctx.deps,
            usage=ctx.usage,          # one shared budget for the whole ticket
            usage_limits=TICKET_LIMITS,
        )
        report = result.output
        self.audit.delegation_result(
            to=desk,
            summary=report.finding,
            ticket_id=ticket_id,
            recommendation=report.recommendation,
            facts_used=report.facts_used,
            actions_taken=report.actions_taken,
            needs_human=report.needs_human,
            confidence=report.confidence.value,
        )
        return report

    # -- delegation tools on the boss --------------------------------------- #

    def _register_delegation_tools(self) -> None:
        team = self

        @self.boss.tool
        async def ask_inventory(ctx: RunContext[TeamDeps], question: str) -> SpecialistReport:
            """Ask the inventory desk about stock, shortfalls, or restock timing.

            Use for: can we fill this, how many are there in that size, when could a
            missing item come back, is a reprint already on order.

            Args:
                question: One specific question. Include facts you already have so the
                    desk does not look them up again.
            """
            return await team._consult("inventory", team.inventory, ctx, question)

        @self.boss.tool
        async def ask_accounting(ctx: RunContext[TeamDeps], question: str) -> SpecialistReport:
            """Ask the accounting desk about cash, bills, margins, or a payment.

            Use for: can we afford this, what is owed, what discount still clears cost,
            should this invoice be paid now. This desk is the only one that can pay.

            Args:
                question: One specific question, including any amount in play.
            """
            return await team._consult("accounting", team.accounting, ctx, question)

        @self.boss.tool
        async def ask_facilities(ctx: RunContext[TeamDeps], question: str) -> SpecialistReport:
            """Ask the facilities desk to verify a lease, rent, or landlord claim.

            Use for: is this rent demand genuine, what does the lease actually say, when
            is rent really due. This desk verifies; it does not pay.

            Args:
                question: One specific question about the premises or the lease.
            """
            return await team._consult("facilities", team.facilities, ctx, question)

        @self.boss.tool
        async def ask_customer_service(
            ctx: RunContext[TeamDeps], question: str
        ) -> SpecialistReport:
            """Ask customer service to draft the reply to the requester.

            Consult this desk **last**, once you know what is true, and pass it the
            confirmed facts. Its drafted message comes back in `recommendation`.

            Args:
                question: What the customer needs to be told, with the confirmed facts.
            """
            return await team._consult(
                "customer_service", team.customer_service, ctx, question
            )

    # -- ticket context ------------------------------------------------------ #

    _current_ticket: int | None = None

    def begin_ticket(self, ticket_id: int) -> None:
        self._current_ticket = ticket_id
        self._delegations.setdefault(ticket_id, 0)
