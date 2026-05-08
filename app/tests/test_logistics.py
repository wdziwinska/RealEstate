from __future__ import annotations

from app.agents.logistics_expert import LogisticsExpert
from app.config import Settings
from app.models import GraphState, PropertyOffer, UserCriteria
from app.tools.cost_tracker import CostTracker
from app.tools.maps import MapsTool


def test_logistics_filters_by_nearest_active_station() -> None:
    settings = Settings(ENABLE_MOCKS=True)
    agent = LogisticsExpert(MapsTool(settings), CostTracker())
    state = GraphState(
        criteria=UserCriteria(max_distance_to_rail_km=1.0),
        offers=[
            PropertyOffer(
                title="Rembertów",
                price_pln=1_100_000,
                area_m2=130,
                address="ul. Chełmżyńska, Warszawa Rembertów",
                municipality="Warszawa",
                district="Rembertów",
                link="https://example.local/r",
            )
        ],
    )

    result = agent.run(state)

    assert len(result.shortlist) == 1
    analysis = result.logistics[result.shortlist[0].id]
    assert analysis.passes_rail_filter is True
    assert analysis.nearest_station == "Warszawa Rembertów"
