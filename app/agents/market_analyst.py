from __future__ import annotations

from app.models import GraphState, WorkflowStatus
from app.tools.cost_tracker import CostTracker
from app.tools.market_data import MarketDataTool


class MarketAnalyst:
    name = "Market Analyst"

    def __init__(self, market_data: MarketDataTool, cost_tracker: CostTracker) -> None:
        self.market_data = market_data
        self.cost_tracker = cost_tracker

    def run(self, state: GraphState) -> GraphState:
        try:
            targets = state.shortlist or state.offers
            for offer in targets:
                state.market[offer.id] = self.market_data.analyze(offer)
            usage = self.cost_tracker.record(
                self.name,
                prompt_tokens=max(60, len(targets) * 45),
                completion_tokens=max(50, len(targets) * 36),
            )
            state.token_costs[self.name] = usage
            return state
        except Exception as exc:
            state.errors.append(f"{self.name}: {exc}")
            state.status = WorkflowStatus.ERROR
            return state
