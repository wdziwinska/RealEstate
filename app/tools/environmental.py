from __future__ import annotations

from app.models import EnvironmentalAnalysis, LogisticsAnalysis, PropertyOffer


class EnvironmentalTool:
    """Mock environmental signal provider for green access and noise risk."""

    GREEN_AREAS = {
        "Rembertów": ["Las Rembertowski", "Rezerwat Kawęczyn"],
        "Sulejówek": ["Lasy sulejóweckie", "tereny zielone przy Długiej"],
        "Ożarów Mazowiecki": ["Park Ołtarzewski"],
        "Piaseczno": ["Chojnowski Park Krajobrazowy"],
        "Legionowo": ["Lasy Chotomowskie", "Rezerwat Ławice Kiełpińskie"],
    }

    NOISE_SOURCES = {
        "Rembertów": ["linia kolejowa Warszawa-Terespol", "ul. Marsa"],
        "Sulejówek": ["linia kolejowa", "droga wojewódzka 637"],
        "Ożarów Mazowiecki": ["DK92", "linia kolejowa"],
        "Piaseczno": ["DK79", "linia kolejowa"],
        "Legionowo": ["linia kolejowa", "droga krajowa 61"],
    }

    def analyze(self, offer: PropertyOffer, logistics: LogisticsAnalysis | None = None) -> EnvironmentalAnalysis:
        key = offer.district or offer.municipality
        green_areas = self.GREEN_AREAS.get(key, ["lokalne skwery i zieleń osiedlowa"])
        noise_sources = self.NOISE_SOURCES.get(key, [])

        green_score = 78.0 if green_areas else 45.0
        if "las" in offer.description.lower():
            green_score += 10
        if logistics and logistics.station_distance_km < 0.5:
            noise_penalty = 16
        elif logistics and logistics.station_distance_km < 1.0:
            noise_penalty = 10
        else:
            noise_penalty = 6
        noise_score = max(0.0, 100.0 - noise_penalty - len(noise_sources) * 5)
        overall = round(green_score * 0.55 + noise_score * 0.45, 1)

        return EnvironmentalAnalysis(
            offer_id=offer.id,
            green_score=round(min(green_score, 100), 1),
            noise_score=round(noise_score, 1),
            overall_score=overall,
            nearby_green_areas=green_areas,
            noise_sources=noise_sources,
            summary=(
                f"Dostęp do zieleni: {', '.join(green_areas)}. "
                f"Główne potencjalne źródła hałasu: {', '.join(noise_sources) or 'brak istotnych w mocku'}."
            ),
        )
