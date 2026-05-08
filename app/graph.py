from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, TypedDict

from app.agents.orchestrator import AgentServices, Orchestrator, create_services
from app.models import GraphState, HitlDecision, UserCriteria, WorkflowStatus
from app.state import ensure_state, state_to_dict

try:
    from langgraph.graph import END, START, StateGraph
except Exception:  # pragma: no cover - fallback for docs/static analysis without deps
    END = "__end__"
    START = "__start__"
    StateGraph = None  # type: ignore[assignment]


Route = Literal[
    "fresh",
    "resume_hitl",
    "researcher_discovery",
    "logistics_filter",
    "parallel_enrichment",
    "hitl_checkpoint",
    "legal_deep_dive",
    "final_synthesis",
    "self_correction",
    "error_handler",
    "end",
]


class GraphStateSchema(TypedDict, total=False):
    criteria: dict[str, Any]
    offers: list[dict[str, Any]]
    shortlist: list[dict[str, Any]]
    logistics: dict[str, dict[str, Any]]
    market: dict[str, dict[str, Any]]
    legal: dict[str, dict[str, Any]]
    environmental: dict[str, dict[str, Any]]
    findings: list[dict[str, Any]]
    hitl_decision: str
    accepted_offer_ids: list[str]
    final_ranking: list[dict[str, Any]]
    errors: list[str]
    token_costs: dict[str, dict[str, Any]]
    api_call_count: int
    status: str
    iteration: int


class RealEstateGraph:
    """LangGraph workflow wrapper with a small imperative fallback."""

    def __init__(self, services: AgentServices | None = None) -> None:
        self.services = services or create_services()
        self.orchestrator = Orchestrator(self.services)
        self.graph = self._build_graph()

    def run(self, state: GraphState) -> GraphState:
        if self.graph is None:
            return self._fallback_run(state)
        result = self.graph.invoke(state_to_dict(state), config={"recursion_limit": 30})
        return ensure_state(result)

    def start(self, criteria: UserCriteria) -> GraphState:
        return self.run(GraphState(criteria=criteria))

    def resume(
        self,
        state: GraphState,
        decision: HitlDecision,
        accepted_offer_ids: list[str] | None = None,
    ) -> GraphState:
        state.hitl_decision = decision
        state.accepted_offer_ids = accepted_offer_ids or []
        return self.run(state)

    def _build_graph(self):
        if StateGraph is None:
            return None

        builder = StateGraph(GraphStateSchema)

        builder.add_node("collect_criteria", self._node(self.orchestrator.collect_criteria))
        builder.add_node("researcher_discovery", self._node(self._researcher_discovery))
        builder.add_node("logistics_filter", self._node(self.orchestrator.logistics_filter))
        builder.add_node("parallel_enrichment", self._node(self.orchestrator.parallel_enrichment))
        builder.add_node("hitl_checkpoint", self._node(self.orchestrator.hitl_checkpoint))
        builder.add_node("legal_deep_dive", self._node(self.orchestrator.legal_deep_dive))
        builder.add_node("final_synthesis", self._node(self.orchestrator.final_synthesis))
        builder.add_node("self_correction", self._node(self.orchestrator.self_correction))
        builder.add_node("error_handler", self._node(self.orchestrator.error_handler))

        builder.add_conditional_edges(
            START,
            self._route_start,
            {
                "fresh": "collect_criteria",
                "resume_hitl": "hitl_checkpoint",
                "error_handler": "error_handler",
            },
        )
        builder.add_edge("collect_criteria", "researcher_discovery")
        builder.add_conditional_edges(
            "researcher_discovery",
            self._route_after_research,
            {
                "logistics_filter": "logistics_filter",
                "self_correction": "self_correction",
                "error_handler": "error_handler",
            },
        )
        builder.add_conditional_edges(
            "logistics_filter",
            self._route_after_logistics,
            {
                "parallel_enrichment": "parallel_enrichment",
                "self_correction": "self_correction",
                "error_handler": "error_handler",
            },
        )
        builder.add_conditional_edges(
            "parallel_enrichment",
            self._route_after_enrichment,
            {
                "hitl_checkpoint": "hitl_checkpoint",
                "self_correction": "self_correction",
                "error_handler": "error_handler",
            },
        )
        builder.add_conditional_edges(
            "hitl_checkpoint",
            self._route_after_hitl,
            {
                "legal_deep_dive": "legal_deep_dive",
                "researcher_discovery": "researcher_discovery",
                "final_synthesis": "final_synthesis",
                "end": END,
            },
        )
        builder.add_edge("self_correction", "researcher_discovery")
        builder.add_edge("legal_deep_dive", "final_synthesis")
        builder.add_edge("final_synthesis", END)
        builder.add_edge("error_handler", END)
        return builder.compile()

    def _node(self, func: Callable[[GraphState], GraphState]) -> Callable[[dict[str, Any]], dict[str, Any]]:
        def wrapper(raw_state: dict[str, Any]) -> dict[str, Any]:
            state = ensure_state(raw_state)
            next_state = func(state)
            return state_to_dict(next_state)

        return wrapper

    def _researcher_discovery(self, state: GraphState) -> GraphState:
        if state.hitl_decision == HitlDecision.REVISE:
            state.hitl_decision = HitlDecision.PENDING
            state.accepted_offer_ids = []
            state.shortlist = []
            state.logistics = {}
            state.market = {}
            state.legal = {}
            state.environmental = {}
            state.final_ranking = []
            state.status = WorkflowStatus.REVISING
        return self.orchestrator.researcher_discovery(state)

    def _route_start(self, raw_state: dict[str, Any]) -> Route:
        state = ensure_state(raw_state)
        if state.status == WorkflowStatus.ERROR:
            return "error_handler"
        if state.status == WorkflowStatus.HITL_WAITING or state.hitl_decision != HitlDecision.PENDING:
            return "resume_hitl"
        return "fresh"

    def _route_after_research(self, raw_state: dict[str, Any]) -> Route:
        state = ensure_state(raw_state)
        if self._has_critical_error(state):
            return "error_handler"
        if not state.offers:
            return "self_correction" if state.iteration < 3 else "error_handler"
        return "logistics_filter"

    def _route_after_logistics(self, raw_state: dict[str, Any]) -> Route:
        state = ensure_state(raw_state)
        if self._has_critical_error(state):
            return "error_handler"
        if not state.shortlist:
            return "self_correction" if state.iteration < 3 else "error_handler"
        if any(offer.id not in state.logistics for offer in state.shortlist):
            return "self_correction"
        return "parallel_enrichment"

    def _route_after_enrichment(self, raw_state: dict[str, Any]) -> Route:
        state = ensure_state(raw_state)
        if self._has_critical_error(state):
            return "error_handler"
        if not state.market or not state.legal or not state.environmental:
            return "self_correction" if state.iteration < 3 else "error_handler"
        return "hitl_checkpoint"

    def _route_after_hitl(self, raw_state: dict[str, Any]) -> Route:
        state = ensure_state(raw_state)
        if state.hitl_decision == HitlDecision.ACCEPTED:
            return "legal_deep_dive"
        if state.hitl_decision == HitlDecision.REVISE:
            return "researcher_discovery"
        if state.hitl_decision == HitlDecision.REJECTED:
            return "final_synthesis"
        return "end"

    def _has_critical_error(self, state: GraphState) -> bool:
        return state.status == WorkflowStatus.ERROR or any("critical" in error.lower() for error in state.errors)

    def _fallback_run(self, state: GraphState) -> GraphState:
        """Fallback mirrors the LangGraph routes when dependencies are unavailable."""

        if state.status == WorkflowStatus.HITL_WAITING or state.hitl_decision != HitlDecision.PENDING:
            state = self.orchestrator.hitl_checkpoint(state)
            if state.hitl_decision == HitlDecision.ACCEPTED:
                state = self.orchestrator.legal_deep_dive(state)
                return self.orchestrator.final_synthesis(state)
            if state.hitl_decision == HitlDecision.REVISE:
                state = self._researcher_discovery(state)
            elif state.hitl_decision == HitlDecision.REJECTED:
                return self.orchestrator.final_synthesis(state)
            else:
                return state
        else:
            state = self.orchestrator.collect_criteria(state)
            state = self.orchestrator.researcher_discovery(state)

        if not state.offers:
            state = self.orchestrator.self_correction(state)
            state = self.orchestrator.researcher_discovery(state)
        state = self.orchestrator.logistics_filter(state)
        if not state.shortlist:
            state = self.orchestrator.self_correction(state)
            state = self.orchestrator.researcher_discovery(state)
            state = self.orchestrator.logistics_filter(state)
        state = self.orchestrator.parallel_enrichment(state)
        return self.orchestrator.hitl_checkpoint(state)


def build_graph(services: AgentServices | None = None) -> RealEstateGraph:
    return RealEstateGraph(services)
