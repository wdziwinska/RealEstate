from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field


class PropertyCondition(StrEnum):
    TO_RENOVATE = "do remontu"
    TO_REFRESH = "do odświeżenia"
    GOOD = "dobry"
    VERY_GOOD = "bardzo dobry"
    HIGH_STANDARD = "standard wysoki"
    UNKNOWN = "Unknown"


class MarketType(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    UNKNOWN = "unknown"


class WorkflowStatus(StrEnum):
    NEW = "new"
    CRITERIA_COLLECTED = "criteria_collected"
    DISCOVERY_DONE = "discovery_done"
    LOGISTICS_DONE = "logistics_done"
    ENRICHMENT_DONE = "enrichment_done"
    HITL_WAITING = "hitl_waiting"
    DEEP_DIVE_DONE = "deep_dive_done"
    COMPLETED = "completed"
    REVISING = "revising"
    ERROR = "error"


class HitlDecision(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVISE = "revise"
    REJECTED = "rejected"


class FindingSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class RiskLevel(StrEnum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    UNKNOWN = "Unknown"


class UserCriteria(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    raw_query: str = Field(default="", description="Original user prompt or criteria.")
    property_type: str = "dom"
    max_price_pln: int = Field(default=1_500_000, gt=0)
    min_area_m2: float | None = Field(default=None, gt=0)
    city: str = "Warszawa"
    search_radius_km: float = Field(default=20.0, gt=0)
    max_distance_to_rail_km: float = Field(default=1.0, gt=0)
    commute_destination: str = "PKP Warszawa Śródmieście"
    target_station: str | None = None
    prefer_green: bool = True
    market_type: MarketType = MarketType.UNKNOWN
    include_primary_market: bool = True
    include_secondary_market: bool = True
    rush_hour: bool = True


class PropertyOffer(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    source: str = "mock_search"
    title: str
    price_pln: int = Field(gt=0)
    area_m2: float = Field(gt=0)
    address: str
    municipality: str
    district: str | None = None
    link: str
    description: str = ""
    photos: list[str] = Field(default_factory=list)
    year_built: int | None = None
    condition: PropertyCondition = PropertyCondition.UNKNOWN
    market_type: MarketType = MarketType.UNKNOWN
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    location: "LocationData | None" = None
    warnings: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def price_per_m2(self) -> float:
        return round(self.price_pln / self.area_m2, 2)


class LocationData(BaseModel):
    offer_id: str | None = None
    latitude: float
    longitude: float
    normalized_address: str
    district: str | None = None
    municipality: str | None = None
    distance_to_warsaw_center_km: float | None = None
    geocoding_source: str = "mock"


class LogisticsAnalysis(BaseModel):
    offer_id: str
    location: LocationData
    nearest_station: str
    station_distance_km: float
    station_active: bool = True
    passes_rail_filter: bool
    drive_minutes: int | None = None
    transit_minutes: int | None = None
    rush_hour_drive_minutes: int | None = None
    rush_hour_transit_minutes: int | None = None
    warnings: list[str] = Field(default_factory=list)


class MarketAnalysis(BaseModel):
    offer_id: str
    price_per_m2: float
    benchmark_price_per_m2: float
    benchmark_scope: str
    market_type: MarketType
    condition: PropertyCondition
    deviation_pct: float
    attractiveness_score: float = Field(ge=0, le=100)
    verdict: str
    warnings: list[str] = Field(default_factory=list)


class LegalAnalysis(BaseModel):
    offer_id: str
    planning_status: str = "Unknown"
    mpzp_documents: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.UNKNOWN
    risk_score: float = Field(default=50.0, ge=0, le=100)
    risks: list[str] = Field(default_factory=list)
    restrictions: list[str] = Field(default_factory=list)
    summary: str = ""
    warnings: list[str] = Field(default_factory=list)


class EnvironmentalAnalysis(BaseModel):
    offer_id: str
    green_score: float = Field(ge=0, le=100)
    noise_score: float = Field(ge=0, le=100)
    overall_score: float = Field(ge=0, le=100)
    nearby_green_areas: list[str] = Field(default_factory=list)
    noise_sources: list[str] = Field(default_factory=list)
    summary: str = ""
    warnings: list[str] = Field(default_factory=list)


class AgentFinding(BaseModel):
    agent_name: str
    offer_id: str | None = None
    severity: FindingSeverity = FindingSeverity.INFO
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CostUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 0


class RankedRecommendation(BaseModel):
    rank: int
    offer_id: str
    title: str
    score: float = Field(ge=0, le=100)
    price_pln: int
    price_per_m2: float
    summary: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class GraphState(BaseModel):
    model_config = ConfigDict(validate_assignment=True, arbitrary_types_allowed=True)

    criteria: UserCriteria = Field(default_factory=UserCriteria)
    offers: list[PropertyOffer] = Field(default_factory=list)
    shortlist: list[PropertyOffer] = Field(default_factory=list)
    logistics: dict[str, LogisticsAnalysis] = Field(default_factory=dict)
    market: dict[str, MarketAnalysis] = Field(default_factory=dict)
    legal: dict[str, LegalAnalysis] = Field(default_factory=dict)
    environmental: dict[str, EnvironmentalAnalysis] = Field(default_factory=dict)
    findings: list[AgentFinding] = Field(default_factory=list)
    hitl_decision: HitlDecision = HitlDecision.PENDING
    accepted_offer_ids: list[str] = Field(default_factory=list)
    final_ranking: list[RankedRecommendation] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    token_costs: dict[str, CostUsage] = Field(default_factory=dict)
    api_call_count: int = 0
    status: WorkflowStatus = WorkflowStatus.NEW
    iteration: int = 0

    def offer_by_id(self, offer_id: str) -> PropertyOffer | None:
        return next((offer for offer in self.offers if offer.id == offer_id), None)

    def add_error(self, message: str) -> None:
        self.errors.append(message)


PropertyOffer.model_rebuild()
GraphState.model_rebuild()