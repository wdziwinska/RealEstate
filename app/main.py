from __future__ import annotations

import asyncio

from app.graph import build_graph
from app.models import HitlDecision, UserCriteria
from app.tools.mcp_clients import shutdown_mcp_clients

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main() -> None:
    """
    Asynchronous main function to run the agent-based real estate search workflow.
    """
    criteria = UserCriteria(
        raw_query=(
            "Dom do 1.5 mln zł, blisko lasu, max 1 km od PKP, Warszawa i okolice. "
            "Dobry dojazd do PKP Warszawa Śródmieście."
        )
    )

    workflow = await build_graph()
    try:
        state = workflow.start(criteria)
        logger.info(f"Status after discovery: {state.status.value}")
        logger.info(f"Offers discovered: {len(state.offers)}")
        logger.info(f"Shortlist: {len(state.shortlist)}")

        if state.shortlist:
            accepted = [offer.id for offer in state.shortlist[:3]]
            final_state = workflow.resume(state, HitlDecision.ACCEPTED, accepted)
            logger.info(f"Final status: {final_state.status.value}")
            for recommendation in final_state.final_ranking:
                logger.info(f"{recommendation.rank}. {recommendation.title} - {recommendation.score}/100")
        else:
            logger.info("No offers were shortlisted. The workflow will now end.")

    finally:
        # Ensure that all MCP server processes are properly shut down.
        await shutdown_mcp_clients()


if __name__ == "__main__":
    # Run the asynchronous main function.
    asyncio.run(main())
