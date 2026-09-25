from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import List

from app.config import Settings
from app.models import LocationData
from app.tools.rate_limiter import RateLimiter
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Station:
    name: str
    latitude: float
    longitude: float
    active: bool = True


class MapsTool:
    """Geocoding, nearest rail station and simple commute estimates."""

    MOCK_COORDINATES = {
        "rembertów": (52.2602, 21.1636),
        "sulejówek": (52.2522, 21.2692),
        "ożarów": (52.2092, 20.7974),
        "piaseczno": (52.0733, 21.0269),
        "legionowo": (52.4015, 20.9266),
        "konstancin": (52.0938, 21.1176),
        "otwock": (52.1058, 21.2613),
        "warszawa": (52.2297, 21.0122),
    }

    STATIONS = [
        Station("Warszawa Rembertów", 52.2590, 21.1610),
        Station("Sulejówek Miłosna", 52.2514, 21.2697),
        Station("Ożarów Mazowiecki", 52.2113, 20.7977),
        Station("Piaseczno", 52.0757, 21.0159),
        Station("Legionowo", 52.4019, 20.9262),
        Station("Otwock", 52.1058, 21.2631),
        Station("Warszawa Śródmieście", 52.2289, 21.0035),
        Station("Warszawa Wawer", 52.2207, 21.1588),
    ]

    DESTINATIONS = {
        "pkp warszawa śródmieście": (52.2289, 21.0035),
        "warszawa śródmieście": (52.2289, 21.0035),
        "centrum": (52.2297, 21.0122),
    }

    def __init__(
        self,
        settings: Settings,
        maps_tools: List[BaseTool] | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self.settings = settings
        self.rate_limiter = rate_limiter or RateLimiter(settings.requests_per_minute, settings.max_retries)
        self.geocode_tool: BaseTool | None = None
        if maps_tools:
            # Find the specific tool for geocoding
            for tool in maps_tools:
                if "geocode" in tool.name.lower():
                    self.geocode_tool = tool
                    logger.info(f"MapsTool initialized with MCP tool: {tool.name}")
                    break
        if not self.geocode_tool:
            logger.info("MapsTool initialized with local mock for geocoding.")

    def geocode(self, offer_id: str, address: str, municipality: str, district: str | None) -> LocationData:
        lat, lon, source = None, None, "mock"
        if self.geocode_tool:
            try:
                tool_input = {"address": address}
                result = self.rate_limiter.run(self.geocode_tool.invoke, tool_input)
                lat = float(result.get("latitude"))
                lon = float(result.get("longitude"))
                source = "mcp"
            except Exception as e:
                logger.warning(f"MCP geocode tool failed: {e}. Falling back to mock.")
                lat, lon = self._mock_coordinates(address, municipality)
        else:
            lat, lon = self._mock_coordinates(address, municipality)

        return self._location_data(offer_id, address, municipality, district, lat, lon, source)

    def _location_data(
                self,
                offer_id: str,
                address: str,
                municipality: str,
                district: str | None,
                lat: float,
                lon: float,
                source: str,
        ) -> LocationData:

        return LocationData(
            offer_id=offer_id,
            latitude=lat,
            longitude=lon,
            normalized_address=f"{address}, {municipality}",
            district=district,
            municipality=municipality,
            distance_to_warsaw_center_km=round(
                haversine_km(
                    lat,
                    lon,
                    self.settings.warsaw_center_lat,
                    self.settings.warsaw_center_lon,
                ),
                2,
            ),
            geocoding_source=source,
        )

    def nearest_active_station(self, latitude: float, longitude: float) -> tuple[Station, float]:
        stations = [station for station in self.STATIONS if station.active]
        nearest = min(
            stations,
            key=lambda station: haversine_km(latitude, longitude, station.latitude, station.longitude),
        )
        distance = haversine_km(latitude, longitude, nearest.latitude, nearest.longitude)
        return nearest, round(distance, 2)

    def commute_times(
        self,
        latitude: float,
        longitude: float,
        destination: str,
        rush_hour: bool = True,
    ) -> dict[str, int]:
        dest_lat, dest_lon = self._destination_coordinates(destination)
        distance = haversine_km(latitude, longitude, dest_lat, dest_lon)
        drive = max(8, round(distance / 38 * 60))
        transit = max(12, round(distance / 28 * 60 + 8))
        return {
            "drive_minutes": drive,
            "transit_minutes": transit,
            "rush_hour_drive_minutes": round(drive * 1.45) if rush_hour else drive,
            "rush_hour_transit_minutes": round(transit * 1.2) if rush_hour else transit,
        }

    def _mock_coordinates(self, address: str, municipality: str) -> tuple[float, float]:
        haystack = f"{address} {municipality}".lower()
        for key, coordinates in self.MOCK_COORDINATES.items():
            if key in haystack:
                return coordinates
        return self.settings.warsaw_center_lat, self.settings.warsaw_center_lon

    def _destination_coordinates(self, destination: str) -> tuple[float, float]:
        normalized = destination.lower().strip()
        for key, coordinates in self.DESTINATIONS.items():
            if key in normalized:
                return coordinates
        return self._mock_coordinates(destination, destination)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
