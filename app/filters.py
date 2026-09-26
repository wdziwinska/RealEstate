from __future__ import annotations

import re
import unicodedata

from app.models import GraphState, LogisticsAnalysis, MarketType, OfferAvailability, PropertyOffer, UserCriteria


PRICE_CAP_PATTERN = re.compile(
    r"\bdo\s+\d[\d\s\u00a0]*(?:[,.]\d+)?(?:\s*(?:mln|milion[a-z]*))?\s*(?:zl|z\u0142|pln)?",
    re.IGNORECASE,
)
DEBUG_FILTER_PATTERN = re.compile(r";?\s*filtry GUI:.*$", re.IGNORECASE)
SEARCH_NOISE_PATTERNS = (
    re.compile(r"\bblisko\s+(?:lasu|parku|zieleni|pkp|stacji|kolei)\b", re.IGNORECASE),
    re.compile(
        r"\bmax\s+\d+(?:[,.]\d+)?\s*km\s+od\s+(?:czynnej\s+)?(?:stacji\s+)?pkp\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:spokojna|cicha|zielona)\s+okolica\b", re.IGNORECASE),
)

LOCATION_HINTS = (
    "otwock",
    "jozefow",
    "karczew",
    "piaseczno",
    "legionowo",
    "pruszkow",
    "sulejowek",
    "milanowek",
    "wawer",
    "rembertow",
    "warszawa",
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


def criteria_search_query(criteria: UserCriteria) -> str:
    raw_query = criteria.raw_query.strip()
    return augment_search_query_with_criteria(raw_query or criteria.property_type, criteria)


def augment_search_query_with_criteria(query: str | None, criteria: UserCriteria) -> str:
    """Build a broad discovery query; precise GUI filters are applied after discovery."""

    base_query = DEBUG_FILTER_PATTERN.sub("", (query or "").strip())
    base_query = PRICE_CAP_PATTERN.sub("", base_query).strip(" ,;")
    base_query = _strip_search_noise(base_query)
    normalized = _normalize(base_query)

    parts = [base_query]

    property_type = criteria.property_type.strip()
    if property_type and _normalize(property_type) not in normalized:
        parts.append(property_type)

    if "sprzedaz" not in normalized and "sprzeda" not in normalized:
        parts.append("na sprzedaz")

    if _should_add_city(base_query, criteria):
        parts.append(criteria.city)

    parts.append(f"do {criteria.max_price_pln} zl")

    return _join_terms(parts)


def criteria_filter_summary(criteria: UserCriteria) -> str:
    parts = [
        f"typ: {criteria.property_type}",
        f"miasto bazowe: {criteria.city}",
        f"promien: {criteria.search_radius_km:g} km",
        f"cena maks.: {criteria.max_price_pln} PLN",
        f"PKP maks.: {criteria.max_distance_to_rail_km:g} km",
    ]

    if criteria.min_area_m2:
        parts.append(f"metraz min.: {criteria.min_area_m2:g} m2")
    if criteria.market_type != MarketType.UNKNOWN:
        parts.append(f"rynek: {criteria.market_type.value}")
    if criteria.prefer_green:
        parts.append("preferuj zielen")

    return "; ".join(parts)


def offer_matches_criteria(
    offer: PropertyOffer,
    criteria: UserCriteria,
    logistics: LogisticsAnalysis | None = None,
) -> bool:
    if offer.availability_status == OfferAvailability.INACTIVE:
        return False

    if offer.price_pln > criteria.max_price_pln:
        return False

    if criteria.min_area_m2 is not None and offer.area_m2 < criteria.min_area_m2:
        return False

    if not _matches_market_type(offer, criteria):
        return False

    if not _matches_property_type(offer, criteria):
        return False

    if not _matches_location(offer, criteria):
        return False

    if logistics is not None:
        if logistics.station_distance_km > criteria.max_distance_to_rail_km:
            return False

        distance_to_center = logistics.location.distance_to_warsaw_center_km
        if _normalize(criteria.city) == "warszawa" and distance_to_center is not None:
            if distance_to_center > criteria.search_radius_km:
                return False

    return True


def filter_offers_by_criteria(
    offers: list[PropertyOffer],
    criteria: UserCriteria,
    state: GraphState | None = None,
) -> list[PropertyOffer]:
    return [
        offer
        for offer in offers
        if offer_matches_criteria(
            offer,
            criteria,
            state.logistics.get(offer.id) if state is not None else None,
        )
    ]


def _matches_market_type(offer: PropertyOffer, criteria: UserCriteria) -> bool:
    if criteria.market_type == MarketType.UNKNOWN:
        return True
    if offer.market_type == MarketType.UNKNOWN:
        return True
    return offer.market_type == criteria.market_type


def _matches_property_type(offer: PropertyOffer, criteria: UserCriteria) -> bool:
    requested = _normalize(criteria.property_type)
    if not requested:
        return True

    haystack = _offer_text(offer)
    if "mieszkan" in requested:
        return "mieszkan" in haystack or "apartament" in haystack or "dom" not in haystack
    if "dom" in requested:
        return "dom" in haystack or "mieszkan" not in haystack

    return requested in haystack or requested.replace(" ", "-") in haystack


def _matches_location(offer: PropertyOffer, criteria: UserCriteria) -> bool:
    city = _normalize(criteria.city)
    if not city or city == "warszawa":
        return True

    haystack = _offer_text(offer)
    return city in haystack


def _offer_text(offer: PropertyOffer) -> str:
    return _normalize(
        " ".join(
            [
                offer.title,
                offer.description,
                offer.address,
                offer.municipality,
                offer.district or "",
                offer.link,
            ]
        )
    )


def _should_add_city(query: str, criteria: UserCriteria) -> bool:
    city = criteria.city.strip()
    if not city:
        return False

    normalized_query = _normalize(query)
    normalized_city = _normalize(city)
    if normalized_city in normalized_query:
        return False

    if normalized_city == "warszawa" and _contains_any(normalized_query, LOCATION_HINTS):
        return False

    return True


def _contains_any(value: str, candidates: tuple[str, ...]) -> bool:
    return any(candidate in value for candidate in candidates)


def _join_terms(parts: list[str]) -> str:
    return re.sub(r"\s+", " ", " ".join(part for part in parts if part)).strip()


def _strip_search_noise(value: str) -> str:
    for pattern in SEARCH_NOISE_PATTERNS:
        value = pattern.sub("", value)
    value = re.sub(r"[,;]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.translate(POLISH_TRANSLATION))
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()
