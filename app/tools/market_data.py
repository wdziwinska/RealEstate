from __future__ import annotations

from app.models import MarketAnalysis, MarketType, PropertyCondition, PropertyOffer


class MarketDataTool:
    """District/municipality benchmark provider with deterministic MVP data."""

    BENCHMARKS = {
        ("Warszawa", "Rembertów", MarketType.SECONDARY): 10_800,
        ("Warszawa", "Rembertów", MarketType.PRIMARY): 12_200,
        ("Sulejówek", None, MarketType.SECONDARY): 9_200,
        ("Ożarów Mazowiecki", None, MarketType.PRIMARY): 10_300,
        ("Piaseczno", None, MarketType.SECONDARY): 8_900,
        ("Legionowo", None, MarketType.SECONDARY): 9_400,
    }

    CONDITION_MULTIPLIERS = {
        PropertyCondition.TO_RENOVATE: 0.84,
        PropertyCondition.TO_REFRESH: 0.94,
        PropertyCondition.GOOD: 1.00,
        PropertyCondition.VERY_GOOD: 1.06,
        PropertyCondition.HIGH_STANDARD: 1.12,
        PropertyCondition.UNKNOWN: 0.97,
    }

    def analyze(self, offer: PropertyOffer) -> MarketAnalysis:
        market_type = offer.market_type if offer.market_type != MarketType.UNKNOWN else MarketType.SECONDARY
        raw_benchmark = self._benchmark(offer.municipality, offer.district, market_type)
        adjusted_benchmark = raw_benchmark * self.CONDITION_MULTIPLIERS[offer.condition]
        deviation = ((offer.price_per_m2 - adjusted_benchmark) / adjusted_benchmark) * 100
        attractiveness = max(0, min(100, 55 - deviation * 1.8))
        verdict = self._verdict(deviation)
        return MarketAnalysis(
            offer_id=offer.id,
            price_per_m2=offer.price_per_m2,
            benchmark_price_per_m2=round(adjusted_benchmark, 2),
            benchmark_scope=self._scope(offer.municipality, offer.district),
            market_type=market_type,
            condition=offer.condition,
            deviation_pct=round(deviation, 2),
            attractiveness_score=round(attractiveness, 1),
            verdict=verdict,
            warnings=[] if offer.condition != PropertyCondition.UNKNOWN else ["Condition unknown."],
        )

    def _benchmark(
        self,
        municipality: str,
        district: str | None,
        market_type: MarketType,
    ) -> float:
        key = (municipality, district, market_type)
        fallback_key = (municipality, None, market_type)
        return float(
            self.BENCHMARKS.get(
                key,
                self.BENCHMARKS.get(fallback_key, 10_000 if market_type == MarketType.PRIMARY else 9_500),
            )
        )

    def _scope(self, municipality: str, district: str | None) -> str:
        return f"{municipality}, {district}" if district else municipality

    def _verdict(self, deviation_pct: float) -> str:
        if deviation_pct <= -10:
            return "Wyraźnie poniżej benchmarku"
        if deviation_pct <= -3:
            return "Lekko poniżej benchmarku"
        if deviation_pct <= 7:
            return "Blisko benchmarku"
        return "Powyżej benchmarku"
