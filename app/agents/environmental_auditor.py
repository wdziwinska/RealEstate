from __future__ import annotations

from app.models import GraphState, WorkflowStatus
from app.tools.cost_tracker import CostTracker
from app.tools.environmental import EnvironmentalTool


class EnvironmentalAuditor:
    name = "Environmental Auditor"

    def __init__(self, environmental_tool: EnvironmentalTool, cost_tracker: CostTracker) -> None:
        self.environmental_tool = environmental_tool
        self.cost_tracker = cost_tracker

    def run(self, state: GraphState) -> GraphState:
        try:
            targets = state.shortlist or state.offers
            for offer in targets:
                state.environmental[offer.id] = self.environmental_tool.analyze(
                    offer,
                    state.logistics.get(offer.id),
                )
            usage = self.cost_tracker.record(
                self.name,
                prompt_tokens=max(60, len(targets) * 35),
                completion_tokens=max(50, len(targets) * 35),
            )
            state.token_costs[self.name] = usage
            return state
        except Exception as exc:
            state.errors.append(f"{self.name}: {exc}")
            state.status = WorkflowStatus.ERROR
            return state
