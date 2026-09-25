from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from app.agents.environmental_auditor import EnvironmentalAuditor
from app.agents.legal_planning_scout import LegalPlanningScout
from app.agents.logistics_expert import LogisticsExpert
from app.agents.market_analyst import MarketAnalyst
from app.agents.researcher import Researcher
from app.config import Settings, get_settings
from app.db.chroma import ChromaStore
from app.db.sqlite import SQLiteStore
from app.models import (
    GraphState,
    HitlDecision,
    RankedRecommendation,
    RiskLevel,
    WorkflowStatus,
)
from app.tools.cost_tracker import CostTracker
from app.tools.environmental import EnvironmentalTool
from app.tools.maps import MapsTool
from app.tools.market_data import MarketDataTool
from app.tools.mcp_clients import get_mcp_tools
from app.tools.pdf_parser import PDFParser
from app.tools.rate_limiter import RateLimiter


@dataclass(slots=True)
class AgentServices:
    settings: Settings
    cost_tracker: CostTracker
    sqlite_store: SQLiteStore
    chroma_store: ChromaStore
    researcher: Researcher
    logistics: LogisticsExpert
    market: MarketAnalyst
    legal: LegalPlanningScout
    environmental: EnvironmentalAuditor


async def create_services(settings: Settings | None = None) -> AgentServices:
    settings = settings or get_settings()
    cost_tracker = CostTracker(settings.openai_model)
    rate_limiter = RateLimiter(settings.requests_per_minute, settings.max_retries)

    # Get tools from the centralized MCP Manager
    web_search_tools = await get_mcp_tools("web-search")
    pdf_tools = await get_mcp_tools("pdf-parser")
    maps_tools = await get_mcp_tools("google-maps")

    pdf_tool = pdf_tools[0] if pdf_tools else None

    sqlite_store = SQLiteStore(settings.sqlite_path)
    chroma_store = ChromaStore(settings.chroma_persist_dir)
    maps_tool = MapsTool(settings, maps_tools=maps_tools, rate_limiter=rate_limiter)

    return AgentServices(
        settings=settings,
        cost_tracker=cost_tracker,
        sqlite_store=sqlite_store,
        chroma_store=chroma_store,
        researcher=Researcher(tools=web_search_tools),
        logistics=LogisticsExpert(maps_tool, cost_tracker),
        market=MarketAnalyst(MarketDataTool(), cost_tracker),
        legal=LegalPlanningScout(PDFParser(pdf_tool=pdf_tool), cost_tracker),
        environmental=EnvironmentalAuditor(EnvironmentalTool(), cost_tracker),
    )


class Orchestrator:
    name = "Orchestrator"

    def __init__(self, services: AgentServices) -> None:
        self.services = services

    async def collect_criteria(self, state: GraphState) -> GraphState:
        state.status = WorkflowStatus.CRITERIA_COLLECTED
        state.iteration += 1
        self.services.sqlite_store.save_state(state)
        return state

    async def researcher_discovery(
            self,
            state: GraphState,
    ) -> GraphState:
        state = await self.services.researcher.run(state)

        self.services.sqlite_store.save_state(state)

        return state

    async def logistics_filter(self, state: GraphState) -> GraphState:
        state = self.services.logistics.run(state)
        self.services.sqlite_store.save_state(state)
        return state

    async def parallel_enrichment(self, state: GraphState) -> GraphState:
        jobs = {
            "market": lambda: self.services.market.run(state.model_copy(deep=True)),
            "legal": lambda: self.services.legal.run(state.model_copy(deep=True), deep=False),
            "environmental": lambda: self.services.environmental.run(state.model_copy(deep=True)),
        }
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(job): name for name, job in jobs.items()}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    state.errors.append(f"{name} enrichment failed: {exc}")
                    state.status = WorkflowStatus.ERROR
                    continue
                state.errors.extend(error for error in result.errors if error not in state.errors)
                state.findings.extend(
                    finding for finding in result.findings if finding not in state.findings
                )
                state.token_costs.update(result.token_costs)
                if name == "market":
                    state.market = result.market
                elif name == "legal":
                    state.legal = result.legal
                elif name == "environmental":
                    state.environmental = result.environmental
                if result.status == WorkflowStatus.ERROR:
                    state.status = WorkflowStatus.ERROR
        if state.status != WorkflowStatus.ERROR:
            state.status = WorkflowStatus.ENRICHMENT_DONE
        self.services.sqlite_store.save_state(state)
        return state

    async def hitl_checkpoint(self, state: GraphState) -> GraphState:
        if state.hitl_decision == HitlDecision.PENDING:
            state.status = WorkflowStatus.HITL_WAITING
        self.services.sqlite_store.save_state(state)
        return state

    async def legal_deep_dive(self, state: GraphState) -> GraphState:
        state = self.services.legal.run(state, deep=True)
        self.services.sqlite_store.save_state(state)
        return state

    async def final_synthesis(self, state: GraphState) -> GraphState:
        if state.hitl_decision == HitlDecision.REJECTED:
            state.final_ranking = []
            state.status = WorkflowStatus.COMPLETED
            self.services.sqlite_store.save_state(state)
            return state
        target_ids = state.accepted_offer_ids or [offer.id for offer in state.shortlist]
        recommendations = []
        for offer in state.shortlist:
            if offer.id not in target_ids:
                continue
            logistics = state.logistics.get(offer.id)
            market = state.market.get(offer.id)
            legal = state.legal.get(offer.id)
            environmental = state.environmental.get(offer.id)

            score = 0.0
            strengths: list[str] = []
            weaknesses: list[str] = []

            if market:
                score += market.attractiveness_score * 0.30
                (strengths if market.deviation_pct <= 0 else weaknesses).append(market.verdict)
            if logistics:
                rail_score = max(0, 100 - logistics.station_distance_km * 60)
                commute_score = max(0, 100 - (logistics.rush_hour_transit_minutes or 60))
                score += (rail_score * 0.15 + commute_score * 0.10)
                strengths.append(
                    f"{logistics.station_distance_km} km do {logistics.nearest_station}"
                )
            if environmental:
                score += environmental.overall_score * 0.20
                if environmental.green_score >= 80:
                    strengths.append("bardzo dobry dostęp do zieleni")
                if environmental.noise_score < 70:
                    weaknesses.append("podwyższone ryzyko hałasu")
            if legal:
                legal_score = {
                    RiskLevel.LOW: 92,
                    RiskLevel.MEDIUM: 62,
                    RiskLevel.HIGH: 25,
                    RiskLevel.UNKNOWN: 45,
                }[legal.risk_level]
                score += legal_score * 0.15
                if legal.risk_level in {RiskLevel.HIGH, RiskLevel.UNKNOWN}:
                    weaknesses.append(f"ryzyko planistyczne: {legal.risk_level.value}")
                else:
                    strengths.append(f"ryzyko planistyczne: {legal.risk_level.value}")
            price_fit = 100 if offer.price_pln <= state.criteria.max_price_pln else 0
            score += price_fit * 0.10

            next_actions = [
                "Zweryfikować księgę wieczystą i pozwolenia/budynek.",
                "Poprosić sprzedającego o rachunki za media i dokumentację remontów.",
                "Sprawdzić hałas w godzinach szczytu podczas wizji lokalnej.",
            ]
            recommendations.append(
                RankedRecommendation(
                    rank=0,
                    offer_id=offer.id,
                    title=offer.title,
                    score=round(min(score, 100), 1),
                    price_pln=offer.price_pln,
                    price_per_m2=offer.price_per_m2,
                    summary=self._summary_for(offer.id, state),
                    strengths=strengths,
                    weaknesses=weaknesses,
                    next_actions=next_actions,
                )
            )

        recommendations.sort(key=lambda recommendation: recommendation.score, reverse=True)
        for index, recommendation in enumerate(recommendations, start=1):
            recommendation.rank = index
        state.final_ranking = recommendations
        state.status = WorkflowStatus.COMPLETED
        self.services.cost_tracker.record(self.name, prompt_tokens=200, completion_tokens=250)
        state.token_costs[self.name] = self.services.cost_tracker.usage_for(self.name)
        self.services.sqlite_store.save_state(state)
        return state

    async def error_handler(self, state: GraphState) -> GraphState:
        state.status = WorkflowStatus.ERROR
        if not state.errors:
            state.errors.append("Critical workflow error.")
        self.services.sqlite_store.save_state(state)
        return state

    async def self_correction(self, state: GraphState) -> GraphState:
        state.errors.append("Incomplete data detected; retrying with relaxed rail distance.")
        state.iteration += 1
        state.hitl_decision = HitlDecision.PENDING
        state.criteria.max_distance_to_rail_km = min(state.criteria.max_distance_to_rail_km + 0.5, 5.0)
        state.status = WorkflowStatus.REVISING
        return state

    def _summary_for(self, offer_id: str, state: GraphState) -> str:
        offer = state.offer_by_id(offer_id)
        logistics = state.logistics.get(offer.id)
        market = state.market.get(offer.id)
        legal = state.legal.get(offer.id)
        environmental = state.environmental.get(offer.id)
        pieces = []
        if offer:
            pieces.append(f"{offer.title}: {offer.price_pln:,} PLN, {offer.price_per_m2:,.0f} PLN/m2")
        if logistics:
            pieces.append(
                f"PKP {logistics.nearest_station} w odległości {logistics.station_distance_km} km"
            )
        if market:
            pieces.append(f"cena {market.deviation_pct:+.1f}% względem benchmarku")
        if environmental:
            pieces.append(f"ocena środowiskowa {environmental.overall_score}/100")
        if legal:
            pieces.append(f"ryzyko prawno-planistyczne {legal.risk_level.value}")
        return "; ".join(pieces) + "."
