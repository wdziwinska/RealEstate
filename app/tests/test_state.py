from __future__ import annotations

from app.models import GraphState, PropertyOffer, UserCriteria


def test_graph_state_roundtrip() -> None:
    state = GraphState(
        criteria=UserCriteria(raw_query="dom pod Warszawą"),
        offers=[
            PropertyOffer(
                title="Test offer",
                price_pln=1_000_000,
                area_m2=120,
                address="Warszawa",
                municipality="Warszawa",
                link="https://example.local/test",
            )
        ],
    )

    restored = GraphState.model_validate_json(state.model_dump_json())

    assert restored.criteria.raw_query == "dom pod Warszawą"
    assert restored.offers[0].price_per_m2 == 8333.33
