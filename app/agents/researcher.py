from __future__ import annotations

import hashlib
import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, List
from urllib.parse import urlparse

from dotenv import load_dotenv
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from app.filters import augment_search_query_with_criteria, criteria_search_query, filter_offers_by_criteria
from app.models import GraphState, MarketType, OfferAvailability, PropertyOffer, UserCriteria, WorkflowStatus
from app.tools.scraper import Scraper

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()


SEARCH_RESULT_PATTERN = re.compile(
    r"\*\*\s*(?P<rank>\d+)\.\s*(?P<title>.+?)\s*\*\*\s*"
    r"\nURL:\s*(?P<link>\S+)\s*"
    r"\nDescription:\s*(?P<description>.*?)(?=\n\n---|\n\n\*\*\s*\d+\.|\Z)",
    re.DOTALL,
)

PRICE_PATTERN = re.compile(
    r"(?P<amount>\d{1,3}(?:[\s\u00a0]\d{3})+(?:[,.]\d{1,2})?|\d+(?:[,.]\d{1,2})?)\s*"
    r"(?P<currency>zł|zl|pln)",
    re.IGNORECASE,
)
MILLION_PRICE_PATTERN = re.compile(
    r"(?P<amount>\d+(?:[,.]\d+)?)\s*(?:mln|milion(?:a|y|ow)?)\s*(?:zł|zl|pln)?",
    re.IGNORECASE,
)
AREA_PATTERN = re.compile(r"(?P<area>\d{2,4}(?:[,.]\d+)?)\s*(?:m2|m²|m\^2)", re.IGNORECASE)

PRICE_LABEL_PATTERN = re.compile(
    r"(?:cena|price)\D{0,30}"
    r"(?P<amount>\d{1,3}(?:[\s\u00a0]\d{3})+(?:[,.]\d{1,2})?)",
    re.IGNORECASE,
)

URL_PATTERN = re.compile(r"https?://[^\s<>\]\)\"']+")

MAX_CATEGORY_EXPANSIONS = 3
MAX_LISTING_LINKS_PER_CATEGORY = 6
MAX_FALLBACK_SEARCHES = 8

MUNICIPALITY_CANDIDATES = (
    "Ozarow Mazowiecki",
    "Minsk Mazowiecki",
    "Konstancin-Jeziorna",
    "Grodzisk Mazowiecki",
    "Warszawa",
    "Rembertow",
    "Sulejowek",
    "Piaseczno",
    "Legionowo",
    "Konstancin",
    "Otwock",
    "Jozefow",
    "Karczew",
    "Pruszkow",
    "Milanowek",
    "Marki",
    "Zabki",
    "Wolomin",
    "Kobylka",
    "Lesznowola",
    "Nadarzyn",
    "Blonie",
)

WARSAW_AREA_FALLBACK_LOCATIONS = (
    "Warszawa",
    "Otwock",
    "Piaseczno",
    "Legionowo",
    "Jozefow",
    "Pruszkow",
    "Sulejowek",
)

FALLBACK_CATEGORY_URLS = {
    "warszawa": (
        "https://warszawa.nieruchomosci-online.pl/domy,sprzedaz/",
        "https://adresowo.pl/domy/warszawa/",
    ),
    "otwock": (
        "https://otwock.nieruchomosci-online.pl/domy,sprzedaz/",
        "https://adresowo.pl/domy/otwock/",
    ),
    "piaseczno": (
        "https://piaseczno.nieruchomosci-online.pl/domy,sprzedaz/",
        "https://adresowo.pl/domy/piaseczno/",
    ),
    "legionowo": (
        "https://legionowo.nieruchomosci-online.pl/domy,sprzedaz/",
        "https://adresowo.pl/domy/legionowo/",
    ),
    "jozefow": (
        "https://jozefow.nieruchomosci-online.pl/domy,sprzedaz/",
        "https://adresowo.pl/domy/jozefow/",
    ),
    "pruszkow": (
        "https://pruszkow.nieruchomosci-online.pl/domy,sprzedaz/",
        "https://adresowo.pl/domy/pruszkow/",
    ),
    "sulejowek": (
        "https://sulejowek.nieruchomosci-online.pl/domy,sprzedaz/",
        "https://adresowo.pl/domy/sulejowek/",
    ),
}

WARSAW_DISTRICTS = {
    "rembertow": "Rembertow",
    "wawer": "Wawer",
}

CATEGORY_URL_MARKERS = (
    "/pl/wyniki/",
    "/domy,sprzedaz",
    "/lista-ofert/",
    "/domy/oferta-sprzedaz/",
    "/nieruchomosci/domy/",
    "/domy/otwock",
    "/domy,",
    "/dom/sprzedaz",
)

CATEGORY_TEXT_MARKERS = (
    "aktualne ogloszenia",
    "sprawdz ",
    "zobacz ",
    "ogloszen - domy",
    "ofert dom",
    "ofert domow",
    "sredniej cenie",
    "kategoria domy",
    "ponizej znajdziesz aktualna oferte",
)

DETAIL_URL_MARKERS = (
    "/pl/oferta/",
    "/d/oferta/",
    "/oferta/",
    "/oferty/",
    "/ogloszenie/",
    "/ogloszenia/",
    "/o/",
    "/ob/",
    "/dom-",
    "/mieszkanie-",
)

INACTIVE_LISTING_MARKERS = (
    "oferta archiwalna",
    "ogloszenie archiwalne",
    "ogloszenie jest archiwalne",
    "oferta nieaktualna",
    "ogloszenie nieaktualne",
    "nieaktualne ogloszenie",
    "nieaktualna oferta",
    "ta oferta jest juz nieaktualna",
    "ogloszenie wygaslo",
    "oferta wygasla",
    "sprzedane",
    "sprzedany",
    "nieruchomosc sprzedana",
    "zostalo sprzedane",
    "zostala sprzedana",
    "usuniete ogloszenie",
    "ogloszenie usuniete",
    "oferta usunieta",
    "nie znaleziono ogloszenia",
    "strona nie istnieje",
    "404 not found",
    "page not found",
    "listing is no longer available",
    "no longer available",
    "sold",
    "expired",
    "archived",
    "removed",
)

ACTIVE_LISTING_MARKERS = (
    "oferta aktualna",
    "ogloszenie aktualne",
    "na sprzedaz",
    "kontakt",
    "zapytaj",
    "umow prezentacje",
    "zadaj pytanie",
    "zobacz telefon",
    "cena",
    "powierzchnia",
)

POLISH_TRANSLATION = str.maketrans(
    {
        "ą": "a",
        "ć": "c",
        "ę": "e",
        "ł": "l",
        "ń": "n",
        "ó": "o",
        "ś": "s",
        "ż": "z",
        "ź": "z",
        "Ą": "A",
        "Ć": "C",
        "Ę": "E",
        "Ł": "L",
        "Ń": "N",
        "Ó": "O",
        "Ś": "S",
        "Ż": "Z",
        "Ź": "Z",
    }
)


class Researcher:
    """
    Agent responsible for discovering real-estate offers
    using Web Search MCP tools.
    """

    name = "Researcher"

    def __init__(
        self,
        tools: List[BaseTool],
        llm: BaseChatModel | None = None,
    ):
        self.tools = tools
        self.scraper = Scraper()

        self.llm = llm or ChatOpenAI(
            model=os.getenv(
                "LOCAL_LLM_MODEL",
                "qwen3:30b",
            ),
            base_url=os.getenv(
                "LOCAL_LLM_BASE_URL",
            ),
            api_key=os.getenv(
                "LOCAL_LLM_API_KEY",
                "dummy",
            ),
            temperature=0,
            max_retries=1,
        )

        self.agent = self.llm.bind_tools(self.tools)

    def _build_query_from_criteria(self, criteria) -> str:
        """
        Build a natural-language search query from UserCriteria
        when raw_query was not provided.
        """

        return criteria_search_query(criteria)

    def _get_search_query(self, state: GraphState) -> str:
        """
        Prefer original user query, but fall back to structured criteria.
        """

        return self._build_query_from_criteria(
            state.criteria
        )

    async def run(self, state: GraphState) -> GraphState:
        search_query = self._get_search_query(state)

        logger.info(
            "Researcher search query: %s",
            repr(search_query),
        )

        messages = [
            SystemMessage(
                content=(
                    "You are the Researcher agent in a real-estate analysis system.\n\n"
                    "Your task is to DISCOVER real property listings.\n"
                    "Do not attempt to validate rail distance, travel time, "
                    "legal status or environmental conditions during discovery. "
                    "Those checks are performed by other agents.\n\n"

                    "Use get-web-search-summaries to find listings matching only "
                    "basic property criteria such as:\n"
                    "- property type\n"
                    "- maximum price\n"
                    "- general location\n"
                    "- minimum area if specified\n\n"

                    "For Warsaw + surrounding area, search broadly. "
                    "Do not put distance-to-PKP requirements into the search query.\n\n"

                    "Return or search for individual listing pages only. "
                    "Avoid portal result pages, category pages, aggregate search pages, "
                    "and pages that only list many offers.\n\n"

                    "Prefer search queries resembling normal Google searches, e.g.:\n"
                    "'dom na sprzedaż Warszawa do 1500000'\n"
                    "'dom na sprzedaż Piaseczno do 1500000'\n"
                    "'dom na sprzedaż Legionowo do 1500000'\n\n"

                    "You MUST use web-search tools."
                )
            ),
            HumanMessage(
                content=(
                    "Find property offers matching the following "
                    "criteria:\n\n"
                    f"{search_query}"
                )
            ),
        ]

        response = self.agent.invoke(messages)

        logger.info(
            "Researcher agent response: %s",
            response,
        )

        logger.info(
            "Researcher tool calls: %s",
            response.tool_calls,
        )

        tool_map = {
            tool.name: tool
            for tool in self.tools
        }
        attempted_queries: list[str] = []

        for call in response.tool_calls or []:
            tool_name = call["name"]
            tool_args = self._tool_args_with_gui_filters(
                call["args"],
                state.criteria,
                tool_name,
            )

            tool = tool_map.get(tool_name)
            logger.info("Tool requested by LLM: %s", tool_name)

            if tool is None:
                logger.error(
                    f"Unknown tool requested by LLM: {tool_name}"
                )
                continue

            logger.info(
                f"Executing MCP tool: {tool_name}"
            )
            logger.info(
                f"Tool arguments: {tool_args}"
            )

            result = await tool.ainvoke(tool_args)

            logger.info(
                "Tool result: %s",
                result,
            )

            tool_query = self._query_from_tool_args(tool_args, fallback=search_query)
            attempted_queries.append(tool_query)
            offers = await self._offers_from_tool_result(
                result,
                state.criteria,
                tool_query,
                tool_map,
            )
            offers = filter_offers_by_criteria(offers, state.criteria)
            added_count = self._add_unique_offers(state, offers)
            logger.info("Researcher stored %d new offers from %s", added_count, tool_name)

        if not state.offers:
            added_count = await self._run_fallback_searches(
                state,
                search_query,
                tool_map,
                attempted_queries,
            )
            logger.info("Researcher fallback stored %d new offers", added_count)

        if state.offers:
            state.status = WorkflowStatus.DISCOVERY_DONE

        return state

    def _query_from_tool_args(self, tool_args: Any, fallback: str) -> str:
        if not isinstance(tool_args, dict):
            return fallback

        for key in ("query", "search_query", "q"):
            value = tool_args.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        return fallback

    def _tool_args_with_gui_filters(
        self,
        tool_args: Any,
        criteria: UserCriteria,
        tool_name: str,
    ) -> Any:
        if not isinstance(tool_args, dict):
            return tool_args
        if tool_name not in {"get-web-search-summaries", "full-web-search"}:
            return tool_args

        next_args = dict(tool_args)
        query_key = next(
            (key for key in ("query", "search_query", "q") if isinstance(next_args.get(key), str)),
            "query",
        )
        next_args[query_key] = augment_search_query_with_criteria(next_args.get(query_key), criteria)
        next_args.setdefault("limit", 10)
        return next_args

    async def _run_fallback_searches(
        self,
        state: GraphState,
        search_query: str,
        tool_map: dict[str, BaseTool],
        attempted_queries: list[str],
    ) -> int:
        search_tool = tool_map.get("get-web-search-summaries")
        added_total = 0
        attempted = {
            self._normalize_query(query)
            for query in attempted_queries
            if query
        }

        if search_tool is not None:
            for fallback_query in self._fallback_search_queries(
                state.criteria,
                search_query,
            ):
                normalized_query = self._normalize_query(fallback_query)
                if normalized_query in attempted:
                    continue
                attempted.add(normalized_query)

                tool_args = self._tool_args_with_gui_filters(
                    {
                        "query": fallback_query,
                        "limit": 10,
                    },
                    state.criteria,
                    search_tool.name,
                )
                tool_query = self._query_from_tool_args(tool_args, fallback=fallback_query)

                logger.info("Fallback MCP search arguments: %s", tool_args)
                try:
                    result = await search_tool.ainvoke(tool_args)
                except Exception as exc:
                    logger.warning("Fallback MCP search failed for %s: %s", tool_query, exc)
                    continue

                logger.info("Fallback MCP search result: %s", result)
                offers = await self._offers_from_tool_result(
                    result,
                    state.criteria,
                    tool_query,
                    tool_map,
                )
                offers = filter_offers_by_criteria(offers, state.criteria)
                added_count = self._add_unique_offers(state, offers)
                added_total += added_count

                if added_count:
                    return added_total

        category_offers = await self._expand_category_results(
            self._fallback_category_results(state.criteria, search_query),
            tool_map,
            state.criteria,
            search_query,
        )
        category_offers = await self._verify_offer_availability(
            category_offers,
            tool_map,
            state.criteria,
        )
        category_offers = filter_offers_by_criteria(category_offers, state.criteria)
        added_total += self._add_unique_offers(state, category_offers)
        return added_total

    def _fallback_search_queries(
        self,
        criteria: UserCriteria,
        search_query: str,
    ) -> list[str]:
        property_type = criteria.property_type.strip() or "nieruchomosc"
        price = int(criteria.max_price_pln)
        candidates = [search_query, criteria_search_query(criteria)]

        for location in self._fallback_locations(criteria, search_query):
            candidates.extend(
                [
                    f"{property_type} na sprzedaz {location} do {price} zl",
                    f"{property_type} {location} do {price} zl oferta",
                    f"site:otodom.pl/pl/oferta {property_type} {location} do {price}",
                    f"site:olx.pl/d/oferta {property_type} {location} do {price}",
                ]
            )

        return self._dedupe_queries(candidates)[:MAX_FALLBACK_SEARCHES]

    def _fallback_category_results(
        self,
        criteria: UserCriteria,
        search_query: str,
    ) -> list[dict[str, str]]:
        results: list[dict[str, str]] = []
        property_type = criteria.property_type.strip() or "nieruchomosc"

        for location in self._fallback_locations(criteria, search_query):
            urls = self._fallback_category_urls(location, property_type)
            for url in urls:
                results.append(
                    {
                        "title": f"{property_type} na sprzedaz {location}",
                        "link": url,
                        "description": (
                            f"Awaryjna strona kategorii dla lokalizacji {location}; "
                            "uzywana, gdy MCP search zwroci 0 wynikow."
                        ),
                    }
                )

        return results

    def _fallback_category_urls(
        self,
        location: str,
        property_type: str,
    ) -> tuple[str, ...]:
        urls = FALLBACK_CATEGORY_URLS.get(self._normalize(location), ())
        if "mieszkan" not in self._normalize(property_type):
            return urls

        return tuple(
            url.replace("/domy,sprzedaz/", "/mieszkania,sprzedaz/")
            .replace("/domy/", "/mieszkania/")
            for url in urls
        )

    def _fallback_locations(
        self,
        criteria: UserCriteria,
        search_query: str,
    ) -> list[str]:
        locations: list[str] = []
        normalized_query = self._normalize(search_query)

        for candidate in MUNICIPALITY_CANDIDATES:
            if self._normalize(candidate) in normalized_query:
                locations.append(candidate)

        if criteria.city:
            locations.append(criteria.city)

        if self._normalize(criteria.city) == "warszawa":
            locations.extend(WARSAW_AREA_FALLBACK_LOCATIONS)

        return self._dedupe_queries(locations)

    def _dedupe_queries(self, queries: list[str]) -> list[str]:
        unique: list[str] = []
        seen: set[str] = set()
        for query in queries:
            cleaned = self._clean_text(query)
            if not cleaned:
                continue
            normalized = self._normalize_query(cleaned)
            if normalized in seen:
                continue
            seen.add(normalized)
            unique.append(cleaned)
        return unique

    def _normalize_query(self, query: str) -> str:
        return re.sub(r"\s+", " ", self._normalize(query)).strip()

    async def _offers_from_tool_result(
        self,
        result: Any,
        criteria: UserCriteria,
        tool_query: str,
        tool_map: dict[str, BaseTool],
    ) -> list[PropertyOffer]:
        offers: list[PropertyOffer] = []
        category_results: list[dict[str, str]] = []
        for text in self._result_text_blocks(result):
            text_offers, text_categories = self._offers_and_categories_from_search_summary_text(
                text,
                criteria,
                tool_query,
            )
            offers.extend(text_offers)
            category_results.extend(text_categories)

        offers.extend(
            await self._expand_category_results(
                category_results,
                tool_map,
                criteria,
                tool_query,
            )
        )
        offers = self._dedupe_offers(offers)
        return await self._verify_offer_availability(offers, tool_map, criteria)

    def _result_text_blocks(self, result: Any) -> list[str]:
        if isinstance(result, str):
            return [result]

        if isinstance(result, dict):
            text = result.get("text")
            if isinstance(text, str) and text.strip():
                return [text]
            content = result.get("content")
            return self._result_text_blocks(content) if content is not None else []

        if isinstance(result, list):
            texts: list[str] = []
            for item in result:
                texts.extend(self._result_text_blocks(item))
            return texts

        text = getattr(result, "text", None)
        if isinstance(text, str) and text.strip():
            return [text]

        content = getattr(result, "content", None)
        if content is not None:
            return self._result_text_blocks(content)

        return []

    def _offers_from_search_summary_text(
        self,
        text: str,
        criteria: UserCriteria,
        tool_query: str,
    ) -> list[PropertyOffer]:
        offers, _ = self._offers_and_categories_from_search_summary_text(
            text,
            criteria,
            tool_query,
        )
        return offers

    def _offers_and_categories_from_search_summary_text(
        self,
        text: str,
        criteria: UserCriteria,
        tool_query: str,
    ) -> tuple[list[PropertyOffer], list[dict[str, str]]]:
        offers: list[PropertyOffer] = []
        category_results: list[dict[str, str]] = []

        for match in SEARCH_RESULT_PATTERN.finditer(text):
            title = self._clean_text(match.group("title"))
            link = match.group("link").strip()
            description = self._clean_text(match.group("description"))
            combined_text = " ".join([title, description, tool_query, link])
            result = {
                "title": title,
                "link": link,
                "description": description,
            }

            if self._looks_like_category_page(combined_text):
                logger.info("Skipping non-listing search result: %s", link)
                category_results.append(result)
                continue

            offer = self._offer_from_listing_result(
                result,
                criteria,
                tool_query,
                source="web_search_mcp",
                base_warnings=["Search result summary; verify source page before decision."],
            )
            if offer is not None:
                offers.append(offer)

        return offers, category_results

    async def _expand_category_results(
        self,
        category_results: list[dict[str, str]],
        tool_map: dict[str, BaseTool],
        criteria: UserCriteria,
        tool_query: str,
    ) -> list[PropertyOffer]:
        offers: list[PropertyOffer] = []
        page_tool = tool_map.get("get-single-web-page-content")
        search_tool = tool_map.get("get-web-search-summaries")

        for category in category_results[:MAX_CATEGORY_EXPANSIONS]:
            category_link = category["link"]

            if page_tool is not None:
                try:
                    page_result = await page_tool.ainvoke(
                        {
                            "url": category_link,
                            "maxContentLength": 15000,
                        }
                    )
                except Exception as exc:
                    logger.warning("Failed to expand listing page %s: %s", category_link, exc)
                else:
                    for text in self._result_text_blocks(page_result):
                        offers.extend(
                            self._offers_from_page_content_text(
                                text,
                                category,
                                criteria,
                                tool_query,
                            )
                        )

            if search_tool is not None:
                followup_query = self._listing_detail_search_query(
                    category,
                    criteria,
                    tool_query,
                )
                try:
                    search_result = await search_tool.ainvoke(
                        {
                            "query": followup_query,
                            "limit": 10,
                        }
                    )
                except Exception as exc:
                    logger.warning("Failed to search listing details for %s: %s", category_link, exc)
                else:
                    for text in self._result_text_blocks(search_result):
                        offers.extend(
                            self._offers_from_search_summary_text(
                                text,
                                criteria,
                                followup_query,
                            )
                        )

        return self._dedupe_offers(offers)

    def _offers_from_page_content_text(
        self,
        text: str,
        category_result: dict[str, str],
        criteria: UserCriteria,
        tool_query: str,
    ) -> list[PropertyOffer]:
        offers: list[PropertyOffer] = []

        for link in self._extract_urls(text):
            if len(offers) >= MAX_LISTING_LINKS_PER_CATEGORY:
                break

            context = self._context_for_url(text, link)
            result = {
                "title": self._title_from_context(context, link, category_result["title"]),
                "link": link,
                "description": self._clean_text(context or category_result["description"]),
            }
            offer = self._offer_from_listing_result(
                result,
                criteria,
                tool_query,
                source="web_search_mcp_expanded",
                base_warnings=[
                    "Offer link extracted from an aggregate page; verify source page before decision."
                ],
            )
            if offer is not None:
                offers.append(offer)

        return self._dedupe_offers(offers)

    async def _verify_offer_availability(
        self,
        offers: list[PropertyOffer],
        tool_map: dict[str, BaseTool],
        criteria: UserCriteria,
    ) -> list[PropertyOffer]:
        page_tool = tool_map.get("get-single-web-page-content")
        verified: list[PropertyOffer] = []

        for offer in offers:
            summary_status, summary_note = self._availability_from_text(
                " ".join([offer.title, offer.description, offer.link]),
                "search summary",
            )
            if summary_status == OfferAvailability.INACTIVE:
                logger.info(
                    "Skipping inactive listing from search summary: %s (%s)",
                    offer.link,
                    summary_note,
                )
                continue

            if page_tool is None:
                offer.availability_status = OfferAvailability.UNKNOWN
                offer.availability_note = "Availability not checked; page-content tool unavailable."
                self._append_warning_once(
                    offer,
                    "Listing availability not verified; page-content tool unavailable.",
                )
                verified.append(offer)
                continue

            checked_offer = await self._offer_with_page_availability(offer, page_tool, criteria)
            if checked_offer.availability_status != OfferAvailability.ACTIVE:
                logger.info(
                    "Skipping listing without confirmed active status: %s (%s)",
                    checked_offer.link,
                    checked_offer.availability_note,
                )
                continue

            verified.append(checked_offer)

        return verified

    async def _offer_with_page_availability(
        self,
        offer: PropertyOffer,
        page_tool: BaseTool,
        criteria: UserCriteria,
    ) -> PropertyOffer:
        offer.availability_checked_at = datetime.now(timezone.utc)
        offer.availability_source = "source_page"

        try:
            page_result = await page_tool.ainvoke(
                {
                    "url": offer.link,
                    "maxContentLength": 15000,
                }
            )
        except Exception as exc:
            offer.availability_status = OfferAvailability.UNKNOWN
            offer.availability_note = f"Availability check failed: {exc}"
            self._append_warning_once(
                offer,
                "Listing availability could not be checked from source page.",
            )
            return offer

        page_text = "\n".join(self._result_text_blocks(page_result))
        status, note = self._availability_from_text(page_text, "source page")
        offer.availability_status = status
        offer.availability_note = note

        if status == OfferAvailability.INACTIVE:
            self._append_warning_once(
                offer,
                "Listing page says the offer is no longer available.",
            )
        elif status == OfferAvailability.UNKNOWN:
            self._append_warning_once(
                offer,
                "Listing availability could not be confirmed from source page.",
            )
        else:
            self._enrich_offer_from_source_page(offer, page_text, criteria)

        return offer

    def _enrich_offer_from_source_page(
        self,
        offer: PropertyOffer,
        page_text: str,
        criteria: UserCriteria,
    ) -> None:
        source_text = self._clean_text(page_text)
        if not source_text:
            return

        if self._text_has_price(source_text):
            price_pln, price_warnings = self._extract_price_pln(source_text, criteria)
            offer.price_pln = price_pln
            for warning in price_warnings:
                self._append_warning_once(offer, warning)

        if AREA_PATTERN.search(source_text):
            area_m2, area_warnings = self._extract_area_m2(
                source_text,
                criteria,
                offer.price_pln,
            )
            offer.area_m2 = area_m2
            for warning in area_warnings:
                self._append_warning_once(offer, warning)

        municipality, district = self._infer_location(
            " ".join([offer.title, source_text, offer.link]),
            criteria,
        )
        offer.municipality = municipality
        offer.district = district
        offer.address = self._address_from_location(municipality, district)
        offer.market_type = self._infer_market_type(source_text, criteria)

        year_built = self.scraper.extract_year_built(source_text)
        if year_built is not None:
            offer.year_built = year_built

        condition = self.scraper.classify_condition(source_text)
        if condition.value != "Unknown":
            offer.condition = condition

        offer.description = self._source_page_description(source_text, offer.description)

    def _text_has_price(self, text: str) -> bool:
        normalized = self._normalize(text)
        return (
            bool(PRICE_PATTERN.search(text))
            or bool(PRICE_LABEL_PATTERN.search(text))
            or bool(MILLION_PRICE_PATTERN.search(normalized))
        )

    def _source_page_description(self, source_text: str, fallback: str) -> str:
        if len(source_text) < max(80, len(fallback)):
            return fallback
        return source_text[:700]

    def _availability_from_text(
        self,
        text: str,
        source: str,
    ) -> tuple[OfferAvailability, str]:
        if not text.strip():
            return OfferAvailability.UNKNOWN, f"No text returned from {source}."

        normalized = self._normalize(text)
        inactive_marker = self._first_marker(normalized, INACTIVE_LISTING_MARKERS)
        if inactive_marker:
            return (
                OfferAvailability.INACTIVE,
                f"{source} contains inactive marker: {inactive_marker}",
            )

        if self._has_active_listing_evidence(text, normalized):
            return OfferAvailability.ACTIVE, f"{source} contains active listing evidence."

        return OfferAvailability.UNKNOWN, f"{source} does not confirm the listing is active."

    def _has_active_listing_evidence(self, text: str, normalized_text: str) -> bool:
        if self._first_marker(normalized_text, ACTIVE_LISTING_MARKERS):
            return True

        has_price = (
            bool(PRICE_PATTERN.search(text))
            or bool(PRICE_LABEL_PATTERN.search(text))
            or bool(MILLION_PRICE_PATTERN.search(normalized_text))
        )
        has_area = bool(AREA_PATTERN.search(text))
        has_contact_hint = any(
            marker in normalized_text
            for marker in (
                "telefon",
                "kontakt",
                "formularz",
                "zapytaj",
                "wyslij wiadomosc",
                "umow",
            )
        )
        return has_price and has_area and has_contact_hint

    def _first_marker(self, text: str, markers: tuple[str, ...]) -> str | None:
        return next((marker for marker in markers if marker in text), None)

    def _append_warning_once(self, offer: PropertyOffer, warning: str) -> None:
        if warning not in offer.warnings:
            offer.warnings.append(warning)

    def _offer_from_listing_result(
        self,
        result: dict[str, str],
        criteria: UserCriteria,
        tool_query: str,
        source: str,
        base_warnings: list[str],
    ) -> PropertyOffer | None:
        title = self._clean_text(result["title"])
        link = self._clean_url(result["link"])
        description = self._clean_text(result["description"])
        listing_text = " ".join([title, description, link])
        combined_text = " ".join([title, description, tool_query, link])

        if not self._is_listing_detail_page(link, combined_text):
            logger.info("Skipping non-detail listing result: %s", link)
            return None

        price_pln, price_warnings = self._extract_price_pln(listing_text, criteria)
        area_m2, area_warnings = self._extract_area_m2(listing_text, criteria, price_pln)
        municipality, district = self._infer_location(listing_text, criteria)
        market_type = self._infer_market_type(listing_text, criteria)
        scraped = self.scraper.scrape_listing(link, description)

        return PropertyOffer(
            id=self._stable_offer_id(link),
            source=source,
            title=title or self._title_from_link(link),
            price_pln=price_pln,
            area_m2=area_m2,
            address=self._address_from_location(municipality, district),
            municipality=municipality,
            district=district,
            link=link,
            description=description,
            year_built=scraped["year_built"],
            condition=scraped["condition"],
            market_type=market_type,
            warnings=[*base_warnings, *price_warnings, *area_warnings],
        )

    def _listing_detail_search_query(
        self,
        category_result: dict[str, str],
        criteria: UserCriteria,
        tool_query: str,
    ) -> str:
        host = urlparse(category_result["link"]).netloc.lower().removeprefix("www.")
        combined_text = " ".join([category_result["title"], category_result["description"], tool_query])
        municipality, _ = self._infer_location(combined_text, criteria)
        site_query = f"site:{host}"

        if "otodom" in host:
            site_query = "site:otodom.pl/pl/oferta"
        elif "olx" in host:
            site_query = "site:olx.pl/d/oferta"
        elif "morizon" in host:
            site_query = "site:morizon.pl/oferta"
        elif "adresowo" in host:
            site_query = "site:adresowo.pl/o/"

        return (
            f"{site_query} {criteria.property_type} {municipality} "
            f"do {criteria.max_price_pln} sprzedaz oferta"
        )

    def _extract_urls(self, text: str) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()
        for match in URL_PATTERN.finditer(text):
            url = self._clean_url(match.group(0))
            if url in seen:
                continue
            seen.add(url)
            urls.append(url)
        return urls

    def _context_for_url(self, text: str, url: str) -> str:
        index = text.find(url)
        if index < 0:
            return ""
        start = max(0, index - 700)
        end = min(len(text), index + len(url) + 700)
        return text[start:end]

    def _title_from_context(self, context: str, link: str, fallback: str) -> str:
        lines = [self._clean_text(line) for line in context.splitlines() if self._clean_text(line)]
        for line in reversed(lines):
            if link in line:
                continue
            if len(line) > 12:
                return line[:160]
        return fallback or self._title_from_link(link)

    def _is_listing_detail_page(self, link: str, text: str) -> bool:
        normalized_link = self._normalize(link)
        normalized_text = self._normalize(text)

        if self._looks_like_category_page(" ".join([link, text])):
            return False

        if any(marker in normalized_link for marker in DETAIL_URL_MARKERS):
            return True

        has_price = (
            bool(PRICE_PATTERN.search(text))
            or bool(PRICE_LABEL_PATTERN.search(text))
            or bool(MILLION_PRICE_PATTERN.search(normalized_text))
        )
        has_area = bool(AREA_PATTERN.search(text))
        generic_title = any(
            marker in normalized_text
            for marker in (
                "domy na sprzedaz",
                "mieszkania na sprzedaz",
                "oferty nieruchomosci",
                "ogloszenia nieruchomosci",
            )
        )
        return has_price and has_area and not generic_title

    def _dedupe_offers(self, offers: list[PropertyOffer]) -> list[PropertyOffer]:
        unique: list[PropertyOffer] = []
        seen_links: set[str] = set()
        for offer in offers:
            if offer.link in seen_links:
                continue
            seen_links.add(offer.link)
            unique.append(offer)
        return unique

    def _add_unique_offers(self, state: GraphState, offers: list[PropertyOffer]) -> int:
        existing_links = {offer.link for offer in state.offers}
        added_count = 0

        for offer in offers:
            if offer.link in existing_links:
                continue

            state.offers.append(offer)
            existing_links.add(offer.link)
            added_count += 1

        return added_count

    def _extract_price_pln(
        self,
        text: str,
        criteria: UserCriteria,
    ) -> tuple[int, list[str]]:
        warnings: list[str] = []
        normalized = self._normalize(text)

        price_matches = [self._parse_number(match.group("amount")) for match in PRICE_PATTERN.finditer(text)]
        price_matches = [price for price in price_matches if price is not None and price > 0]

        if not price_matches:
            price_matches = [
                self._parse_number(match.group("amount"))
                for match in PRICE_PATTERN.finditer(normalized)
            ]
            price_matches = [price for price in price_matches if price is not None and price > 0]

        if not price_matches:
            price_matches = [
                self._parse_number(match.group("amount"))
                for match in PRICE_LABEL_PATTERN.finditer(text)
            ]
            price_matches = [price for price in price_matches if price is not None and price > 0]

        if not price_matches:
            for match in MILLION_PRICE_PATTERN.finditer(normalized):
                raw_value = match.group("amount").replace(",", ".")
                try:
                    price_matches.append(int(float(raw_value) * 1_000_000))
                except ValueError:
                    continue

        if price_matches:
            if "sredniej cenie" in normalized or "ceny od" in normalized:
                warnings.append("Price comes from a search snippet/category summary; verify exact price.")
            return int(price_matches[0]), warnings

        warnings.append("Price missing in search summary; using criteria max price as fallback.")
        return int(criteria.max_price_pln), warnings

    def _extract_area_m2(
        self,
        text: str,
        criteria: UserCriteria,
        price_pln: int,
    ) -> tuple[float, list[str]]:
        for match in AREA_PATTERN.finditer(text):
            raw_value = match.group("area").replace(",", ".")
            try:
                area = float(raw_value)
            except ValueError:
                continue

            if area > 0:
                return area, []

        fallback_area = criteria.min_area_m2 or max(60.0, min(280.0, round(price_pln / 10_000, 1)))
        return fallback_area, ["Area missing in search summary; using estimated fallback."]

    def _infer_location(
        self,
        text: str,
        criteria: UserCriteria,
    ) -> tuple[str, str | None]:
        normalized = self._normalize(text)

        for district_key, district_name in WARSAW_DISTRICTS.items():
            if district_key in normalized:
                return "Warszawa", district_name

        for candidate in MUNICIPALITY_CANDIDATES:
            if self._normalize(candidate) in normalized:
                if candidate in {"Rembertow"}:
                    return "Warszawa", candidate
                if candidate == "Konstancin":
                    return "Konstancin-Jeziorna", None
                return candidate, None

        return criteria.city or "Warszawa", None

    def _infer_market_type(self, text: str, criteria: UserCriteria) -> MarketType:
        normalized = self._normalize(text)
        if "pierwotny" in normalized or "deweloper" in normalized or "nowy dom" in normalized:
            return MarketType.PRIMARY
        if "wtorny" in normalized:
            return MarketType.SECONDARY
        return MarketType.UNKNOWN

    def _looks_like_category_page(self, text: str) -> bool:
        normalized = self._normalize(text)
        return any(marker in normalized for marker in CATEGORY_URL_MARKERS) or any(
            marker in normalized for marker in CATEGORY_TEXT_MARKERS
        )

    def _address_from_location(self, municipality: str, district: str | None) -> str:
        if district:
            return f"{district}, {municipality}"
        return municipality

    def _stable_offer_id(self, link: str) -> str:
        digest = hashlib.sha1(link.encode("utf-8")).hexdigest()[:12]
        return f"web-{digest}"

    def _clean_url(self, value: str) -> str:
        return value.strip().rstrip(".,;:)]}")

    def _title_from_link(self, link: str) -> str:
        path = urlparse(link).path.strip("/")
        if not path:
            return urlparse(link).netloc
        slug = path.split("/")[-1]
        slug = re.sub(r"[-_]+", " ", slug)
        return self._clean_text(slug).title()

    def _clean_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    def _normalize(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value.translate(POLISH_TRANSLATION))
        ascii_value = "".join(char for char in normalized if not unicodedata.combining(char))
        return ascii_value.lower()

    def _parse_number(self, value: str) -> int | None:
        normalized = value.replace("\u00a0", " ").strip()
        if "," in normalized:
            integer_part, decimal_part = normalized.rsplit(",", 1)
            if len(decimal_part) <= 2:
                normalized = integer_part
        normalized = re.sub(r"\D", "", normalized)
        return int(normalized) if normalized else None
