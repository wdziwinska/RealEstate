from __future__ import annotations

from app.agents.orchestrator import create_services
from app.config import Settings
from app.graph import RealEstateGraph
from app.models import HitlDecision, UserCriteria, WorkflowStatus


def test_graph_reaches_hitl_and_resumes_to_final_ranking(tmp_path) -> None:
    settings = Settings(
        ENABLE_MOCKS=True,
        DATABASE_URL=f"sqlite:///{tmp_path / 'state.db'}",
        CHROMA_PERSIST_DIR=tmp_path / ".chroma",
    )
    workflow = RealEstateGraph(create_services(settings))

    state = workflow.start(
        UserCriteria(
            raw_query="Dom do 1.5 mln, blisko lasu, max 1 km od PKP",
            max_distance_to_rail_km=1.0,
        )
    )

    assert state.status == WorkflowStatus.HITL_WAITING
    assert state.shortlist

    accepted_ids = [offer.id for offer in state.shortlist[:2]]
    final_state = workflow.resume(state, HitlDecision.ACCEPTED, accepted_ids)

    assert final_state.status == WorkflowStatus.COMPLETED
    assert final_state.final_ranking
    assert {item.offer_id for item in final_state.final_ranking} <= set(accepted_ids)
