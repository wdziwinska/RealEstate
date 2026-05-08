from __future__ import annotations

from app.models import MarketType, PropertyCondition, PropertyOffer
from app.tools.market_data import MarketDataTool


def test_market_analysis_uses_condition_adjusted_benchmark() -> None:
    offer = PropertyOffer(
        title="Segment",
        price_pln=1_190_000,
        area_m2=128,
        address="Sulejówek",
        municipality="Sulejówek",
        link="https://example.local/s",
        condition=PropertyCondition.GOOD,
        market_type=MarketType.SECONDARY,
    )

    analysis = MarketDataTool().analyze(offer)

    assert analysis.benchmark_price_per_m2 == 9200
    assert analysis.price_per_m2 == 9296.88
    assert analysis.deviation_pct > 0
