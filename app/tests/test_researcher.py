from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.agents.researcher import Researcher
from app.models import GraphState, MarketType, OfferAvailability, UserCriteria, WorkflowStatus
from app.tools.scraper import Scraper


class FakeAgent:
    def invoke(self, messages):
        return SimpleNamespace(
            tool_calls=[
                {
                    "name": "get-web-search-summaries",
                    "args": {"query": "dom na sprzedaż Otwock do 2500000"},
                }
            ]
        )


class FakeSearchTool:
    name = "get-web-search-summaries"

    async def ainvoke(self, args):
        return [
            {
                "type": "text",
                "text": (
                    'Search summaries for "dom na sprzedaż Otwock do 2500000" with 2 results:\n\n'
                    "**1. Domy na sprzedaż Otwock - Sprzedam dom w Otwocku**\n"
                    "URL: https://example-real-estate.pl/oferta/dom-wolnostojacy-otwock-123\n"
                    "Description: Dom wolnostojący 180 m2 z 2000 r., cena 1 450 000 zł, Otwock.\n\n"
                    "---\n\n"
                    "**2. Domy na sprzedaż Otwock | Gratka**\n"
                    "URL: https://gratka.pl/nieruchomosci/domy/otwock\n"
                    "Description: 19 ogłoszeń - domy na sprzedaż Otwock - ceny od 503 000 zł.\n\n"
                    "---\n\n"
                ),
            }
        ]


class FakeCategorySearchTool:
    name = "get-web-search-summaries"

    async def ainvoke(self, args):
        return [
            {
                "type": "text",
                "text": (
                    'Search summaries for "dom na sprzedaĹĽ Otwock do 2500000" with 1 results:\n\n'
                    "**1. Domy na sprzedaĹĽ Otwock | Portal**\n"
                    "URL: https://portal.example/domy/otwock\n"
                    "Description: Aktualne ogĹ‚oszenia domĂłw na sprzedaĹĽ w Otwocku.\n\n"
                    "---\n\n"
                ),
            }
        ]


class FakePageTool:
    name = "get-single-web-page-content"

    async def ainvoke(self, args):
        return [
            {
                "type": "text",
                "text": (
                    "Nowa oferta: Dom wolnostojÄ…cy Otwock MlÄ…dz, 210 m2, 2015 r., "
                    "cena 1 980 000 zĹ‚. "
                    "https://portal.example/oferta/dom-wolnostojacy-otwock-mladz-456"
                ),
            }
        ]


class FakeActiveDetailPageTool:
    name = "get-single-web-page-content"

    async def ainvoke(self, args):
        return [
            {
                "type": "text",
                "text": (
                    "Oferta aktualna. Dom wolnostojacy Otwock, powierzchnia 180 m2, "
                    "cena 1 450 000 zl. Kontakt do sprzedajacego."
                ),
            }
        ]


class FakeInactiveDetailPageTool:
    name = "get-single-web-page-content"

    async def ainvoke(self, args):
        return [
            {
                "type": "text",
                "text": "Ta oferta jest juz nieaktualna. Ogloszenie archiwalne.",
            }
        ]


class RecordingSearchTool:
    name = "get-web-search-summaries"

    def __init__(self):
        self.calls = []

    async def ainvoke(self, args):
        self.calls.append(args)
        return []


class EmptyThenOfferSearchTool:
    name = "get-web-search-summaries"

    def __init__(self):
        self.calls = []

    async def ainvoke(self, args):
        self.calls.append(args)
        if len(self.calls) == 1:
            return [
                {
                    "type": "text",
                    "text": 'Search summaries for "dom Otwock" with 0 results:\n\n',
                }
            ]

        return [
            {
                "type": "text",
                "text": (
                    'Search summaries for "fallback" with 1 results:\n\n'
                    "**1. Dom wolnostojacy Otwock Mlacz**\n"
                    "URL: https://example-real-estate.pl/oferta/dom-otwock-fallback-789\n"
                    "Description: Dom Otwock, 140 m2, cena 1 350 000 zl, rynek wtorny.\n\n"
                    "---\n\n"
                ),
            }
        ]


def test_researcher_stores_search_results_as_offers() -> None:
    researcher = Researcher.__new__(Researcher)
    researcher.tools = [FakeSearchTool()]
    researcher.agent = FakeAgent()
    researcher.scraper = Scraper()

    state = GraphState(criteria=UserCriteria(max_price_pln=2_500_000))

    result = asyncio.run(researcher.run(state))

    assert result.status == WorkflowStatus.DISCOVERY_DONE
    assert len(result.offers) == 1
    assert result.offers[0].municipality == "Otwock"
    assert result.offers[0].price_pln == 1_450_000
    assert result.offers[0].area_m2 == 180
    assert result.offers[0].year_built == 2000
    assert result.offers[0].link == "https://example-real-estate.pl/oferta/dom-wolnostojacy-otwock-123"
    assert result.offers[0].warnings


def test_researcher_marks_offer_active_when_source_page_confirms_it() -> None:
    researcher = Researcher.__new__(Researcher)
    researcher.scraper = Scraper()
    criteria = UserCriteria(max_price_pln=2_500_000)
    search_result = asyncio.run(FakeSearchTool().ainvoke({}))

    offers = asyncio.run(
        researcher._offers_from_tool_result(
            search_result,
            criteria,
            "dom na sprzedaz Otwock do 2500000",
            {"get-single-web-page-content": FakeActiveDetailPageTool()},
        )
    )

    assert len(offers) == 1
    assert offers[0].availability_status == OfferAvailability.ACTIVE
    assert offers[0].availability_checked_at is not None
    assert offers[0].availability_source == "source_page"


def test_researcher_drops_inactive_source_page_offers() -> None:
    researcher = Researcher.__new__(Researcher)
    researcher.scraper = Scraper()
    criteria = UserCriteria(max_price_pln=2_500_000)
    search_result = asyncio.run(FakeSearchTool().ainvoke({}))

    offers = asyncio.run(
        researcher._offers_from_tool_result(
            search_result,
            criteria,
            "dom na sprzedaz Otwock do 2500000",
            {"get-single-web-page-content": FakeInactiveDetailPageTool()},
        )
    )

    assert offers == []


def test_researcher_expands_category_results_to_detail_offers() -> None:
    researcher = Researcher.__new__(Researcher)
    researcher.tools = [FakeCategorySearchTool(), FakePageTool()]
    researcher.agent = FakeAgent()
    researcher.scraper = Scraper()

    state = GraphState(criteria=UserCriteria(max_price_pln=2_500_000))

    result = asyncio.run(researcher.run(state))

    assert result.status == WorkflowStatus.DISCOVERY_DONE
    assert len(result.offers) == 1
    assert result.offers[0].link == "https://portal.example/oferta/dom-wolnostojacy-otwock-mladz-456"
    assert result.offers[0].price_pln == 1_980_000
    assert result.offers[0].area_m2 == 210


def test_researcher_passes_gui_filters_to_search_tool() -> None:
    search_tool = RecordingSearchTool()
    researcher = Researcher.__new__(Researcher)
    researcher.tools = [search_tool]
    researcher.agent = FakeAgent()
    researcher.scraper = Scraper()

    state = GraphState(
        criteria=UserCriteria(
            raw_query="spokojna okolica",
            property_type="dom",
            max_price_pln=1_700_000,
            min_area_m2=120,
            city="Otwock",
            search_radius_km=15,
            max_distance_to_rail_km=1.2,
            market_type=MarketType.SECONDARY,
        )
    )

    asyncio.run(researcher.run(state))

    assert search_tool.calls
    query = search_tool.calls[0]["query"]
    assert "Otwock" in query
    assert "do 1700000 zl" in query
    assert "2500000" not in query
    assert "filtry GUI" not in query
    assert "cena maks." not in query
    assert "blisko PKP" not in query
    assert search_tool.calls[0]["limit"] == 10


def test_researcher_runs_fallback_when_search_returns_zero() -> None:
    search_tool = EmptyThenOfferSearchTool()
    researcher = Researcher.__new__(Researcher)
    researcher.tools = [search_tool]
    researcher.agent = FakeAgent()
    researcher.scraper = Scraper()

    state = GraphState(
        criteria=UserCriteria(
            property_type="dom",
            max_price_pln=1_500_000,
            city="Otwock",
            market_type=MarketType.SECONDARY,
        )
    )

    result = asyncio.run(researcher.run(state))

    assert len(search_tool.calls) >= 2
    assert result.status == WorkflowStatus.DISCOVERY_DONE
    assert len(result.offers) == 1
    assert result.offers[0].link == "https://example-real-estate.pl/oferta/dom-otwock-fallback-789"
    assert result.offers[0].price_pln == 1_350_000
