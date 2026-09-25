from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.agents.researcher import Researcher
from app.models import GraphState, UserCriteria, WorkflowStatus
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
