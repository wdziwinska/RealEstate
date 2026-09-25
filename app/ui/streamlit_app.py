from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from app.graph import RealEstateGraph, build_graph
from app.models import GraphState, HitlDecision, MarketType, UserCriteria, WorkflowStatus
from app.tools.cost_tracker import CostTracker


def get_workflow() -> RealEstateGraph:
    """
    Retrieves the workflow graph instance from the session state, creating it if necessary.
    Handles the asynchronous creation of the graph in a synchronous context.
    """
    if "workflow" not in st.session_state:
        # build_graph is an async function, so we need to run it in an event loop.
        # asyncio.run() creates a new event loop and closes it, which is suitable here.
        st.session_state.workflow = asyncio.run(build_graph())
    return st.session_state.workflow


def current_state() -> GraphState | None:
    state = st.session_state.get("graph_state")
    return state if isinstance(state, GraphState) else None


def build_criteria_form(existing: GraphState | None) -> UserCriteria:
    criteria = existing.criteria if existing else UserCriteria()
    with st.sidebar:
        st.header("Kryteria")
        raw_query = st.text_area("Opis", value=criteria.raw_query, height=120)
        property_type = st.text_input("Typ nieruchomości", value=criteria.property_type)
        max_price = st.number_input(
            "Maks. cena PLN",
            min_value=100_000,
            max_value=10_000_000,
            value=criteria.max_price_pln,
            step=50_000,
        )
        min_area = st.number_input(
            "Min. metraż m2",
            min_value=0,
            max_value=1000,
            value=int(criteria.min_area_m2 or 0),
            step=5,
        )
        city = st.text_input("Miasto bazowe", value=criteria.city)
        search_radius = st.slider("Promień od Warszawy km", 1.0, 30.0, criteria.search_radius_km, 1.0)
        rail_distance = st.slider(
            "Maks. odległość do czynnej stacji PKP km",
            0.2,
            5.0,
            criteria.max_distance_to_rail_km,
            0.1,
        )
        commute_destination = st.text_input(
            "Punkt docelowy dojazdu",
            value=criteria.commute_destination,
        )
        market_label = st.selectbox(
            "Rynek",
            ["Dowolny", "Pierwotny", "Wtórny"],
            index={MarketType.UNKNOWN: 0, MarketType.PRIMARY: 1, MarketType.SECONDARY: 2}[
                criteria.market_type
            ],
        )
        prefer_green = st.checkbox("Preferuj bliskość zieleni", value=criteria.prefer_green)
        rush_hour = st.checkbox("Uwzględnij godziny szczytu", value=criteria.rush_hour)

    market_type = {
        "Dowolny": MarketType.UNKNOWN,
        "Pierwotny": MarketType.PRIMARY,
        "Wtórny": MarketType.SECONDARY,
    }[market_label]
    return UserCriteria(
        raw_query=raw_query,
        property_type=property_type,
        max_price_pln=int(max_price),
        min_area_m2=float(min_area) if min_area else None,
        city=city,
        search_radius_km=float(search_radius),
        max_distance_to_rail_km=float(rail_distance),
        commute_destination=commute_destination,
        prefer_green=prefer_green,
        market_type=market_type,
        include_primary_market=market_type in {MarketType.UNKNOWN, MarketType.PRIMARY},
        include_secondary_market=market_type in {MarketType.UNKNOWN, MarketType.SECONDARY},
        rush_hour=rush_hour,
    )


def offer_rows(state: GraphState, shortlist_only: bool = False) -> list[dict[str, object]]:
    offers = state.shortlist if shortlist_only else state.offers
    rows = []
    for offer in offers:
        logistics = state.logistics.get(offer.id)
        market = state.market.get(offer.id)
        legal = state.legal.get(offer.id)
        environmental = state.environmental.get(offer.id)
        rows.append(
            {
                "id": offer.id,
                "tytuł": offer.title,
                "gmina/dzielnica": f"{offer.municipality} {offer.district or ''}".strip(),
                "cena": offer.price_pln,
                "m2": offer.area_m2,
                "PLN/m2": offer.price_per_m2,
                "rok": offer.year_built or "Unknown",
                "stan": offer.condition.value,
                "PKP km": logistics.station_distance_km if logistics else None,
                "stacja": logistics.nearest_station if logistics else None,
                "dojazd szczyt min": logistics.rush_hour_transit_minutes if logistics else None,
                "benchmark %": market.deviation_pct if market else None,
                "legal": legal.risk_level.value if legal else None,
                "środowisko": environmental.overall_score if environmental else None,
            }
        )
    return rows


def render_costs(state: GraphState) -> None:
    total = CostTracker().total()
    total.prompt_tokens = sum(usage.prompt_tokens for usage in state.token_costs.values())
    total.completion_tokens = sum(usage.completion_tokens for usage in state.token_costs.values())
    total.cost_usd = round(sum(usage.cost_usd for usage in state.token_costs.values()), 6)
    total.calls = sum(usage.calls for usage in state.token_costs.values())
    col1, col2, col3 = st.columns(3)
    col1.metric("API calls", state.api_call_count)
    col2.metric("Tokens", total.prompt_tokens + total.completion_tokens)
    col3.metric("Est. cost USD", f"{total.cost_usd:.4f}")
    with st.expander("Koszt per agent"):
        st.dataframe(
            [
                {
                    "agent": agent,
                    "prompt": usage.prompt_tokens,
                    "completion": usage.completion_tokens,
                    "calls": usage.calls,
                    "USD": usage.cost_usd,
                }
                for agent, usage in state.token_costs.items()
            ],
            hide_index=True,
            use_container_width=True,
        )


def render_offer_details(state: GraphState) -> None:
    st.subheader("Szczegóły ofert")
    for offer in state.shortlist or state.offers:
        with st.expander(offer.title):
            st.write(offer.description)
            st.write(f"Link: {offer.link}")
            logistics = state.logistics.get(offer.id)
            market = state.market.get(offer.id)
            legal = state.legal.get(offer.id)
            environmental = state.environmental.get(offer.id)
            if logistics:
                st.write(
                    f"PKP: {logistics.nearest_station}, {logistics.station_distance_km} km. "
                    f"Auto: {logistics.drive_minutes} min, komunikacja szczyt: "
                    f"{logistics.rush_hour_transit_minutes} min."
                )
            if market:
                st.write(
                    f"Rynek: {market.market_type.value}, benchmark: "
                    f"{market.benchmark_price_per_m2:,.0f} PLN/m2, {market.verdict}."
                )
            if legal:
                st.write(f"Legal/planning: {legal.summary}")
                if legal.risks:
                    st.write("Ryzyka: " + "; ".join(legal.risks))
                if legal.warnings:
                    st.warning("; ".join(legal.warnings))
            if environmental:
                st.write(environmental.summary)
            if offer.warnings:
                st.warning("; ".join(offer.warnings))


def main() -> None:
    st.set_page_config(page_title="Real Estate Agents MVP", layout="wide")
    st.title("Autonomiczna selekcja nieruchomości")
    st.caption("MVP wieloagentowy: discovery, logistyka, rynek, MPZP, środowisko, HITL.")

    existing = current_state()
    criteria = build_criteria_form(existing)
    workflow = get_workflow()

    start_col, reset_col = st.columns([1, 4])
    if start_col.button("Start analysis", type="primary"):
        with st.spinner("Agenci analizują oferty..."):
            st.session_state.graph_state = asyncio.run(
                workflow.start(criteria)
            )
    if reset_col.button("Reset"):
        st.session_state.pop("graph_state", None)
        st.rerun()

    state = current_state()
    if state is None:
        st.info("Podaj kryteria i uruchom analizę.")
        return

    st.subheader("Status")
    st.write(f"`{state.status.value}`")
    if state.errors:
        st.warning("\n".join(state.errors))

    render_costs(state)

    if state.offers:
        st.subheader("Discovery")
        st.dataframe(offer_rows(state), hide_index=True, use_container_width=True)

    if state.shortlist:
        st.subheader("Shortlista po filtrze PKP")
        st.dataframe(offer_rows(state, shortlist_only=True), hide_index=True, use_container_width=True)

    if state.status == WorkflowStatus.HITL_WAITING:
        st.subheader("Checkpoint HITL")
        options = {f"{offer.title} ({offer.id[:8]})": offer.id for offer in state.shortlist}
        selected_labels = st.multiselect(
            "Wybierz oferty do deep dive",
            options=list(options.keys()),
            default=list(options.keys())[: min(3, len(options))],
        )
        selected_ids = [options[label] for label in selected_labels]
        accept_col, revise_col, reject_col = st.columns(3)
        if accept_col.button("Accept selected", type="primary", disabled=not selected_ids):
            with st.spinner("Deep dive MPZP i synteza rankingu..."):
                st.session_state.graph_state = workflow.resume(
                    state,
                    HitlDecision.ACCEPTED,
                    selected_ids,
                )
                st.rerun()
        if revise_col.button("Revise criteria"):
            state.criteria = criteria
            with st.spinner("Ponawiam discovery po zmianie kryteriów..."):
                st.session_state.graph_state = workflow.resume(state, HitlDecision.REVISE)
                st.rerun()
        if reject_col.button("Reject"):
            st.session_state.graph_state = workflow.resume(state, HitlDecision.REJECTED)
            st.rerun()

    if state.final_ranking:
        st.subheader("Finalny ranking")
        st.dataframe(
            [
                {
                    "rank": item.rank,
                    "tytuł": item.title,
                    "score": item.score,
                    "cena": item.price_pln,
                    "PLN/m2": item.price_per_m2,
                    "uzasadnienie": item.summary,
                }
                for item in state.final_ranking
            ],
            hide_index=True,
            use_container_width=True,
        )
        for item in state.final_ranking:
            with st.expander(f"#{item.rank} {item.title}"):
                st.write(item.summary)
                st.write("Mocne strony: " + "; ".join(item.strengths or ["brak"]))
                st.write("Słabości: " + "; ".join(item.weaknesses or ["brak"]))
                st.write("Następne kroki: " + "; ".join(item.next_actions))
    elif state.status == WorkflowStatus.COMPLETED and state.hitl_decision == HitlDecision.REJECTED:
        st.info("Analiza zakończona bez rekomendacji po odrzuceniu shortlisty.")

    render_offer_details(state)


if __name__ == "__main__":
    main()
