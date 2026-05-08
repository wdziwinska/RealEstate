from __future__ import annotations

import re

from app.models import PropertyCondition


class Scraper:
    """Mock-friendly extraction helpers used after web-search snippets."""

    YEAR_PATTERN = re.compile(r"\b(19[4-9]\d|20[0-2]\d)\b")

    CONDITION_KEYWORDS: list[tuple[PropertyCondition, tuple[str, ...]]] = [
        (PropertyCondition.TO_RENOVATE, ("do remontu", "generalny remont", "wymaga remontu")),
        (PropertyCondition.TO_REFRESH, ("do odświeżenia", "do odswiezenia", "odświeżenia")),
        (PropertyCondition.HIGH_STANDARD, ("wysoki standard", "premium", "luksusowy")),
        (PropertyCondition.VERY_GOOD, ("bardzo dobry", "po remoncie", "gotowy do wprowadzenia")),
        (PropertyCondition.GOOD, ("dobry", "zadbany", "komfortowy")),
    ]

    def extract_year_built(self, text: str) -> int | None:
        matches = [int(match.group(1)) for match in self.YEAR_PATTERN.finditer(text)]
        plausible = [year for year in matches if 1940 <= year <= 2026]
        return plausible[0] if plausible else None

    def classify_condition(self, text: str) -> PropertyCondition:
        normalized = text.lower()
        for condition, keywords in self.CONDITION_KEYWORDS:
            if any(keyword in normalized for keyword in keywords):
                return condition
        return PropertyCondition.UNKNOWN

    def scrape_listing(self, url: str, fallback_description: str) -> dict[str, object]:
        """Return extracted listing facts. Real scraping can be plugged in here."""

        description = fallback_description or ""
        return {
            "url": url,
            "year_built": self.extract_year_built(description),
            "condition": self.classify_condition(description),
            "blocked": False,
        }
