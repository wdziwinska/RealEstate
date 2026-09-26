from __future__ import annotations

from app.models import (
    AgentFinding,
    FindingSeverity,
    GraphState,
    LogisticsAnalysis,
    WorkflowStatus,
)
from app.tools.cost_tracker import CostTracker
from app.tools.maps import MapsTool


class LogisticsExpert:
    name = "Logistics Expert"

    def __init__(self, maps_tool: MapsTool, cost_tracker: CostTracker) -> None:
        self.maps_tool = maps_tool
        self.cost_tracker = cost_tracker

    def run(self, state: GraphState) -> GraphState:
        shortlist = []
        try:
            for offer in state.offers:
                analysis = self.analyze_offer(state, offer.id)
                state.logistics[offer.id] = analysis
                offer.location = analysis.location
                distance_to_center = analysis.location.distance_to_warsaw_center_km
                passes_radius_filter = (
                    distance_to_center is None
                    or distance_to_center <= state.criteria.search_radius_km
                )
                if analysis.passes_rail_filter and passes_radius_filter:
                    shortlist.append(offer)
                else:
                    reasons = [
                        f"{analysis.station_distance_km} km to {analysis.nearest_station}"
                    ]
                    if not analysis.station_active:
                        reasons.append("station is inactive")
                    if not passes_radius_filter and distance_to_center is not None:
                        reasons.append(f"{distance_to_center} km from Warsaw center")
                    state.findings.append(
                        AgentFinding(
                            agent_name=self.name,
                            offer_id=offer.id,
                            severity=FindingSeverity.INFO,
                            message="Rejected by logistics filters: " + "; ".join(reasons) + ".",
                        )
                    )
            state.shortlist = shortlist
            state.status = WorkflowStatus.LOGISTICS_DONE
            usage = self.cost_tracker.record(
                self.name,
                prompt_tokens=max(50, len(state.offers) * 35),
                completion_tokens=max(40, len(state.offers) * 30),
            )
            state.token_costs[self.name] = usage
            state.api_call_count += len(state.offers) * 2
        except Exception as exc:
            state.errors.append(f"{self.name}: {exc}")
            state.status = WorkflowStatus.ERROR
        return state

    def analyze_offer(self, state: GraphState, offer_id: str) -> LogisticsAnalysis:
        offer = state.offer_by_id(offer_id)
        if offer is None:
            raise ValueError(f"Offer not found: {offer_id}")
        location = self.maps_tool.geocode(offer.id, offer.address, offer.municipality, offer.district)
        station, distance_km = self.maps_tool.nearest_active_station(
            location.latitude,
            location.longitude,
        )
        commute = self.maps_tool.commute_times(
            location.latitude,
            location.longitude,
            state.criteria.commute_destination,
            rush_hour=state.criteria.rush_hour,
        )
        warnings = []
        if location.geocoding_source == "mock":
            warnings.append("Google Maps/MCP geocoding unavailable; mock coordinates used.")

        return LogisticsAnalysis(
            offer_id=offer.id,
            location=location,
            nearest_station=station.name,
            station_distance_km=distance_km,
            station_active=station.active,
            passes_rail_filter=station.active and distance_km <= state.criteria.max_distance_to_rail_km,
            warnings=warnings,
            **commute,
        )
