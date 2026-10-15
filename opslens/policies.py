"""Policies: who works on which ticket. One interface, `decide(state, now) -> list[Assignment]`.

Baselines (the status quo we must beat):
- **Baseline A — FIFO.** Each free agent takes the oldest waiting ticket from their own
  team's queue. Only when that queue has nothing they can serve do they help with their
  extra skills. Routing uses the category the customer picked (or the real one, once an
  agent has read the ticket after a transfer).
- **Baseline B — priority.** Same, but P1 before P2 before P3, oldest first inside a priority.

Both are fair, realistic floors: language is always respected, agents never take tickets
outside their skills on purpose, and longest-idle agents choose first.
The OpsLens policy (risk + optimiser) is added in M7 with the same interface.

Example: agent B03 (Team B, English) is free. Waiting: T1 refund P2 created 10:00,
T2 payment P1 created 10:05, T3 late_delivery P1 created 09:50 (Team A's queue).
Baseline A gives B03 T1 (oldest in Team B's queue). Baseline B gives B03 T2 (P1 first).
"""

from __future__ import annotations

from typing import Callable

from opslens.simulate import AgentView, Assignment, SimState, TicketView

PRIORITY_RANK = {"P1": 0, "P2": 1, "P3": 2}


def routing_category(ticket: TicketView) -> str:
    """What the status-quo floor believes the ticket is about."""
    return ticket.known_category or ticket.selected_category


class TeamQueuePolicy:
    """Shared logic of both baselines; they differ only in how a queue is sorted."""

    def __init__(self, name: str, sort_key: Callable[[TicketView], tuple]) -> None:
        self.name = name
        self._sort_key = sort_key

    def decide(self, state: SimState, now: float) -> list[Assignment]:
        free = state.free_agents(now)
        if not free:
            return []
        queue = sorted(state.waiting_tickets(), key=self._sort_key)
        taken: set[int] = set()
        assignments: list[Assignment] = []
        for agent in free:
            for _ in range(agent.free_slots):
                ticket = self._pick(agent, queue, taken)
                if ticket is None:
                    break
                taken.add(ticket.idx)
                category = routing_category(ticket)
                own = category in agent.team_skills
                assignments.append(
                    Assignment(
                        ticket_idx=ticket.idx,
                        agent_id=agent.agent_id,
                        believed_category=category,
                        reason=f"{self.name}: {'own queue' if own else 'helping with extra skill'}",
                    )
                )
        return assignments

    @staticmethod
    def _pick(agent: AgentView, queue: list[TicketView], taken: set[int]) -> TicketView | None:
        """First ticket in the agent's own team queue; else first one in their extra skills."""
        extra_choice: TicketView | None = None
        for ticket in queue:
            if ticket.idx in taken or ticket.language not in agent.languages:
                continue
            category = routing_category(ticket)
            if category in agent.team_skills:
                return ticket
            if extra_choice is None and category in agent.skills:
                extra_choice = ticket
        return extra_choice


def baseline_a() -> TeamQueuePolicy:
    """FIFO: oldest ticket first."""
    return TeamQueuePolicy("Baseline A (FIFO)", sort_key=lambda t: (t.created_min, t.idx))


def baseline_b() -> TeamQueuePolicy:
    """Priority first (P1, P2, P3), then oldest."""
    return TeamQueuePolicy(
        "Baseline B (priority)", sort_key=lambda t: (PRIORITY_RANK[t.priority], t.created_min, t.idx)
    )
