from __future__ import annotations

from app.filters import augment_search_query_with_criteria, criteria_search_query, filter_offers_by_criteria
from app.models import MarketType, OfferAvailability, PropertyOffer, UserCriteria


def test_criteria_search_query_includes_gui_filters() -> None:
    criteria = UserCriteria(
        raw_query="spokojna okolica",
        property_type="dom",
        max_price_pln=1_700_000,
        min_area_m2=120,
        city="Otwock",
        search_radius_km=15,
        max_distance_to_rail_km=1.2,
        market_type=MarketType.SECONDARY,
    )

    query = criteria_search_query(criteria)

    assert "spokojna okolica" not in query
    assert "dom" in query
    assert "Otwock" in query
    assert "do 1700000 zl" in query
    assert "od 120 m2" in query
    assert "rynek wtorny" in query
    assert "blisko PKP" not in query
    assert "filtry GUI" not in query
    assert "cena maks." not in query


def test_augment_search_query_keeps_location_and_uses_clean_filter_terms() -> None:
    criteria = UserCriteria(
        property_type="dom",
        max_price_pln=1_500_000,
        min_area_m2=140,
        city="Warszawa",
        max_distance_to_rail_km=2,
        prefer_green=True,
        market_type=MarketType.SECONDARY,
    )

    query = augment_search_query_with_criteria(
        "dom na sprzedaz Otwock do 2500000 od 80 m2 rynek pierwotny; filtry GUI: cena maks.: 2500000 PLN",
        criteria,
    )

    assert "Otwock" in query
    assert "Warszawa" not in query
    assert "do 1500000 zl" in query
    assert "od 140 m2" in query
    assert "80 m2" not in query
    assert "rynek wtorny" in query
    assert "rynek pierwotny" not in query
    assert "2500000" not in query
    assert "blisko PKP" not in query
    assert "blisko lasu" not in query
    assert "blisko parku" not in query
    assert "filtry GUI" not in query
    assert "cena maks." not in query


def test_filter_offers_by_criteria_applies_gui_values() -> None:
    criteria = UserCriteria(
        property_type="dom",
        max_price_pln=1_700_000,
        min_area_m2=120,
        city="Otwock",
        market_type=MarketType.SECONDARY,
    )
    matching_offer = PropertyOffer(
        title="Dom wolnostojacy Otwock",
        price_pln=1_650_000,
        area_m2=140,
        address="Otwock",
        municipality="Otwock",
        link="https://example.test/oferta/dom-1",
        market_type=MarketType.SECONDARY,
    )
    too_expensive = matching_offer.model_copy(
        update={
            "id": "too-expensive",
            "link": "https://example.test/oferta/dom-2",
            "price_pln": 1_900_000,
        }
    )
    too_small = matching_offer.model_copy(
        update={
            "id": "too-small",
            "link": "https://example.test/oferta/dom-3",
            "area_m2": 90,
        }
    )
    wrong_city = matching_offer.model_copy(
        update={
            "id": "wrong-city",
            "link": "https://example.test/oferta/dom-4",
            "municipality": "Piaseczno",
            "address": "Piaseczno",
            "title": "Dom wolnostojacy Piaseczno",
        }
    )

    filtered = filter_offers_by_criteria(
        [matching_offer, too_expensive, too_small, wrong_city],
        criteria,
    )

    assert filtered == [matching_offer]


def test_filter_offers_by_criteria_keeps_property_type_specific() -> None:
    criteria = UserCriteria(property_type="dom", max_price_pln=900_000, city="Otwock")
    house_offer = PropertyOffer(
        title="Dom wolnostojacy Otwock",
        price_pln=850_000,
        area_m2=120,
        address="Otwock",
        municipality="Otwock",
        link="https://example.test/oferta/dom",
    )
    apartment_offer = PropertyOffer(
        title="Apartament Otwock centrum",
        price_pln=650_000,
        area_m2=60,
        address="Otwock",
        municipality="Otwock",
        link="https://example.test/oferta/apartament",
    )

    filtered = filter_offers_by_criteria([house_offer, apartment_offer], criteria)

    assert filtered == [house_offer]


def test_filter_offers_by_criteria_excludes_inactive_offers() -> None:
    criteria = UserCriteria(property_type="dom", max_price_pln=1_700_000, city="Otwock")
    active_offer = PropertyOffer(
        title="Dom wolnostojacy Otwock",
        price_pln=1_650_000,
        area_m2=140,
        address="Otwock",
        municipality="Otwock",
        link="https://example.test/oferta/dom-active",
        availability_status=OfferAvailability.ACTIVE,
    )
    inactive_offer = active_offer.model_copy(
        update={
            "id": "inactive",
            "link": "https://example.test/oferta/dom-inactive",
            "availability_status": OfferAvailability.INACTIVE,
        }
    )

    filtered = filter_offers_by_criteria([active_offer, inactive_offer], criteria)

    assert filtered == [active_offer]
