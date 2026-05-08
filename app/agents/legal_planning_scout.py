from __future__ import annotations

from app.models import GraphState, LegalAnalysis, RiskLevel, WorkflowStatus
from app.tools.cost_tracker import CostTracker
from app.tools.pdf_parser import PDFParser


class LegalPlanningScout:
    name = "Legal & Planning Scout"

    def __init__(self, pdf_parser: PDFParser, cost_tracker: CostTracker) -> None:
        self.pdf_parser = pdf_parser
        self.cost_tracker = cost_tracker

    def run(self, state: GraphState, deep: bool = False) -> GraphState:
        try:
            targets = self._targets(state, deep=deep)
            for offer in targets:
                state.legal[offer.id] = self.analyze_offer(offer.id, state, deep=deep)
            usage = self.cost_tracker.record(
                self.name,
                prompt_tokens=max(80, len(targets) * (90 if deep else 45)),
                completion_tokens=max(70, len(targets) * (80 if deep else 30)),
            )
            state.token_costs[self.name] = usage
            if deep:
                state.status = WorkflowStatus.DEEP_DIVE_DONE
            return state
        except Exception as exc:
            state.errors.append(f"{self.name}: {exc}")
            state.status = WorkflowStatus.ERROR
            return state

    def analyze_offer(self, offer_id: str, state: GraphState, deep: bool = False) -> LegalAnalysis:
        offer = state.offer_by_id(offer_id)
        if offer is None:
            raise ValueError(f"Offer not found: {offer_id}")

        risks: list[str] = []
        restrictions: list[str] = []
        docs: list[str] = []
        warnings: list[str] = []
        risk_score = 24.0
        planning_status = "MPZP likely available or to verify in municipality portal"

        location_key = f"{offer.municipality} {offer.district or ''}".lower()
        description = offer.description.lower()
        if "ożarów" in location_key:
            risks.extend(["DK92 corridor impact", "possible logistics/warehouse pressure"])
            restrictions.append("Verify buffers from service roads and industrial zoning.")
            risk_score += 24
        if "rembert" in location_key:
            risks.append("Rail corridor and major road noise should be checked in MPZP.")
            risk_score += 12
        if "piaseczno" in location_key:
            risks.append("Renovation scope may require additional technical/legal diligence.")
            restrictions.append("Check building permits and as-built documentation.")
            risk_score += 18
        if "kolej" in description or "pkp" in description:
            risks.append("Rail proximity requires noise map verification.")
            risk_score += 6

        if deep:
            docs = self._mock_documents(offer.municipality)
            extracted_text = "\n".join(self.pdf_parser.extract_text(doc) for doc in docs)
            if docs and not extracted_text.strip():
                warnings.append("MPZP PDF unreadable in MVP mock/local parser; legal risk remains partly Unknown.")
                risk_score += 8
            if "przemysł" in extracted_text.lower():
                risks.append("PDF mentions industrial zoning near the analyzed area.")
                risk_score += 12

        risk_level = self._risk_level(risk_score)
        if warnings and deep:
            risk_level = RiskLevel.UNKNOWN if risk_level == RiskLevel.LOW else risk_level

        return LegalAnalysis(
            offer_id=offer.id,
            planning_status=planning_status,
            mpzp_documents=docs,
            risk_level=risk_level,
            risk_score=round(min(risk_score, 100), 1),
            risks=risks or ["No major planning red flags found in MVP mock analysis."],
            restrictions=restrictions,
            summary=self._summary(risks, risk_level, deep),
            warnings=warnings,
        )

    def _targets(self, state: GraphState, deep: bool) -> list:
        if deep and state.accepted_offer_ids:
            return [offer for offer in state.shortlist if offer.id in state.accepted_offer_ids]
        return state.shortlist or state.offers

    def _mock_documents(self, municipality: str) -> list[str]:
        slug = (
            municipality.lower()
            .replace(" ", "-")
            .replace("ó", "o")
            .replace("ł", "l")
            .replace("ń", "n")
            .replace("ś", "s")
        )
        return [f"mock://mpzp/{slug}/plan.pdf"]

    def _risk_level(self, risk_score: float) -> RiskLevel:
        if risk_score >= 70:
            return RiskLevel.HIGH
        if risk_score >= 42:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _summary(self, risks: list[str], risk_level: RiskLevel, deep: bool) -> str:
        mode = "Deep dive" if deep else "Screening"
        return f"{mode}: legal/planning risk assessed as {risk_level.value}. " + (
            "Key risks: " + "; ".join(risks) if risks else "No material red flags in mock data."
        )
