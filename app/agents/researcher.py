from __future__ import annotations

from app.db.chroma import ChromaStore
from app.models import (
    AgentFinding,
    FindingSeverity,
    GraphState,
    PropertyCondition,
    WorkflowStatus,
)
from app.tools.cost_tracker import CostTracker
from app.tools.scraper import Scraper
from app.tools.web_search import WebSearchTool


class Researcher:
    name = "Researcher"

    def __init__(
        self,
        web_search: WebSearchTool,
        scraper: Scraper,
        cost_tracker: CostTracker,
        chroma_store: ChromaStore | None = None,
    ) -> None:
        self.web_search = web_search
        self.scraper = scraper
        self.cost_tracker = cost_tracker
        self.chroma_store = chroma_store

    def run(self, state: GraphState) -> GraphState:
        try:
            offers = self.web_search.search_offers(state.criteria, max_results=10)
            enriched = []
            for offer in offers:
                scraped = self.scraper.scrape_listing(offer.link, offer.description)
                if offer.year_built is None:
                    offer.year_built = scraped["year_built"]  # type: ignore[assignment]
                if offer.condition == PropertyCondition.UNKNOWN:
                    offer.condition = scraped["condition"]  # type: ignore[assignment]
                if offer.year_built is None:
                    warning = "Year built unknown; queued for image/text follow-up."
                    offer.warnings.append(warning)
                    state.findings.append(
                        AgentFinding(
                            agent_name=self.name,
                            offer_id=offer.id,
                            severity=FindingSeverity.WARNING,
                            message=warning,
                        )
                    )
                if self.chroma_store:
                    self.chroma_store.upsert_offer(offer)
                enriched.append(offer)

            state.offers = enriched
            state.status = WorkflowStatus.DISCOVERY_DONE
            usage = self.cost_tracker.record(
                self.name,
                prompt_tokens=sum(len(offer.description.split()) for offer in enriched) * 2,
                completion_tokens=max(80, len(enriched) * 45),
            )
            state.token_costs[self.name] = usage
            state.api_call_count += 1
            if not enriched:
                state.findings.append(
                    AgentFinding(
                        agent_name=self.name,
                        severity=FindingSeverity.WARNING,
                        message="No offers found for current criteria.",
                    )
                )
        except Exception as exc:
            state.errors.append(f"{self.name}: {exc}")
            state.status = WorkflowStatus.ERROR
        return state
