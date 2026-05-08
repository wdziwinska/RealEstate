from __future__ import annotations

from typing import Any

from app.models import MarketType, PropertyCondition, PropertyOffer, UserCriteria
from app.tools.mcp_clients import MCPClientError, MCPWebSearchClient
from app.tools.rate_limiter import RateLimiter


class WebSearchTool:
    """Search facade. It uses MCP when configured and deterministic mock data otherwise."""

    def __init__(
        self,
        mcp_client: MCPWebSearchClient | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self.mcp_client = mcp_client or MCPWebSearchClient()
        self.rate_limiter = rate_limiter or RateLimiter()

    def search_offers(self, criteria: UserCriteria, max_results: int = 10) -> list[PropertyOffer]:
        query = (
            f"{criteria.property_type} {criteria.city} okolice {criteria.search_radius_km} km "
            f"do {criteria.max_price_pln} PLN blisko PKP las"
        )
        if not self.mcp_client.enabled:
            return self._mock_offers(criteria)[:max_results]
        try:
            raw_results = self.rate_limiter.run(self.mcp_client.search, query, max_results)
            return [self._offer_from_result(result) for result in raw_results]
        except (MCPClientError, NotImplementedError):
            return self._mock_offers(criteria)[:max_results]

    def _offer_from_result(self, result: dict[str, Any]) -> PropertyOffer:
        return PropertyOffer.model_validate(result)

    def _mock_offers(self, criteria: UserCriteria) -> list[PropertyOffer]:
        offers = [
            PropertyOffer(
                source="mock_otodom",
                title="Dom przy lesie, Rembertów",
                price_pln=1_340_000,
                area_m2=142,
                address="ul. Chełmżyńska, Warszawa Rembertów",
                municipality="Warszawa",
                district="Rembertów",
                link="https://example.local/oferty/rembertow-dom-las",
                description=(
                    "Dom z 2012 roku, bardzo dobry stan, w pobliżu lasu i stacji PKP "
                    "Warszawa Rembertów. Rynek wtórny."
                ),
                photos=["https://example.local/images/rembertow-1.jpg"],
                year_built=2012,
                condition=PropertyCondition.VERY_GOOD,
                market_type=MarketType.SECONDARY,
            ),
            PropertyOffer(
                source="mock_morizon",
                title="Segment w Sulejówku niedaleko PKP",
                price_pln=1_190_000,
                area_m2=128,
                address="ul. Dworcowa, Sulejówek",
                municipality="Sulejówek",
                district=None,
                link="https://example.local/oferty/sulejowek-segment",
                description=(
                    "Segment z 2008 roku, stan dobry, 900 m do stacji PKP Sulejówek Miłosna. "
                    "Blisko zieleń miejska."
                ),
                photos=["https://example.local/images/sulejowek-1.jpg"],
                year_built=2008,
                condition=PropertyCondition.GOOD,
                market_type=MarketType.SECONDARY,
            ),
            PropertyOffer(
                source="mock_rynekpierwotny",
                title="Nowy dom w Ożarowie Mazowieckim",
                price_pln=1_470_000,
                area_m2=156,
                address="ul. Poznańska, Ożarów Mazowiecki",
                municipality="Ożarów Mazowiecki",
                district=None,
                link="https://example.local/oferty/ozarow-nowy-dom",
                description=(
                    "Nowa inwestycja, wysoki standard, pompa ciepła, dojazd do PKP Ożarów "
                    "Mazowiecki. Oddanie 2025."
                ),
                photos=["https://example.local/images/ozarow-1.jpg"],
                year_built=2025,
                condition=PropertyCondition.HIGH_STANDARD,
                market_type=MarketType.PRIMARY,
            ),
            PropertyOffer(
                source="mock_gratka",
                title="Dom do remontu w Piasecznie",
                price_pln=990_000,
                area_m2=170,
                address="ul. Sienkiewicza, Piaseczno",
                municipality="Piaseczno",
                district=None,
                link="https://example.local/oferty/piaseczno-remont",
                description=(
                    "Duży dom wymaga remontu, rok budowy niepodany, około 1.8 km od PKP "
                    "Piaseczno. Atrakcyjna działka."
                ),
                photos=["https://example.local/images/piaseczno-1.jpg"],
                year_built=None,
                condition=PropertyCondition.TO_RENOVATE,
                market_type=MarketType.SECONDARY,
            ),
            PropertyOffer(
                source="mock_olx",
                title="Bliźniak w Legionowie przy lesie",
                price_pln=1_280_000,
                area_m2=136,
                address="ul. Jagiellońska, Legionowo",
                municipality="Legionowo",
                district=None,
                link="https://example.local/oferty/legionowo-blizniak",
                description=(
                    "Bliźniak po remoncie, gotowy do wprowadzenia, blisko lasu. Do stacji "
                    "PKP Legionowo około 1.2 km."
                ),
                photos=["https://example.local/images/legionowo-1.jpg"],
                year_built=None,
                condition=PropertyCondition.VERY_GOOD,
                market_type=MarketType.SECONDARY,
            ),
            PropertyOffer(
                source="mock_otodom",
                title="Dom premium w Konstancinie",
                price_pln=2_300_000,
                area_m2=220,
                address="ul. Warszawska, Konstancin-Jeziorna",
                municipality="Konstancin-Jeziorna",
                district=None,
                link="https://example.local/oferty/konstancin-premium",
                description="Luksusowy dom premium, daleko od kolei, blisko uzdrowiska.",
                photos=["https://example.local/images/konstancin-1.jpg"],
                year_built=2018,
                condition=PropertyCondition.HIGH_STANDARD,
                market_type=MarketType.SECONDARY,
            ),
        ]
        filtered = [
            offer
            for offer in offers
            if offer.price_pln <= criteria.max_price_pln
            and (criteria.min_area_m2 is None or offer.area_m2 >= criteria.min_area_m2)
            and (
                offer.market_type != MarketType.PRIMARY
                or criteria.include_primary_market
            )
            and (
                offer.market_type != MarketType.SECONDARY
                or criteria.include_secondary_market
            )
        ]
        return filtered or offers[:3]
