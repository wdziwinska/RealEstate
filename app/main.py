from __future__ import annotations

from app.graph import build_graph
from app.models import HitlDecision, UserCriteria


def main() -> None:
    criteria = UserCriteria(
        raw_query=(
            "Dom do 1.5 mln zł, blisko lasu, max 1 km od PKP, Warszawa i okolice. "
            "Dobry dojazd do PKP Warszawa Śródmieście."
        )
    )
    workflow = build_graph()
    state = workflow.start(criteria)
    print(f"Status after discovery: {state.status.value}")
    print(f"Offers discovered: {len(state.offers)}")
    print(f"Shortlist: {len(state.shortlist)}")
    accepted = [offer.id for offer in state.shortlist[:3]]
    final_state = workflow.resume(state, HitlDecision.ACCEPTED, accepted)
    print(f"Final status: {final_state.status.value}")
    for recommendation in final_state.final_ranking:
        print(f"{recommendation.rank}. {recommendation.title} - {recommendation.score}/100")


if __name__ == "__main__":
    main()
