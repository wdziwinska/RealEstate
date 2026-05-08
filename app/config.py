from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with mock-first defaults for local MVP runs."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o", alias="OPENAI_MODEL")

    tavily_api_key: str | None = Field(default=None, alias="TAVILY_API_KEY")
    firecrawl_api_key: str | None = Field(default=None, alias="FIRECRAWL_API_KEY")
    google_maps_api_key: str | None = Field(default=None, alias="GOOGLE_MAPS_API_KEY")

    mcp_web_search_url: str | None = Field(default=None, alias="MCP_WEB_SEARCH_URL")
    mcp_google_maps_url: str | None = Field(default=None, alias="MCP_GOOGLE_MAPS_URL")
    mcp_pdf_url: str | None = Field(default=None, alias="MCP_PDF_URL")
    mcp_database_url: str | None = Field(default=None, alias="MCP_DATABASE_URL")

    database_url: str = Field(default="sqlite:///real_estate_agents.db", alias="DATABASE_URL")
    chroma_persist_dir: Path = Field(default=Path(".chroma"), alias="CHROMA_PERSIST_DIR")

    requests_per_minute: int = Field(default=30, ge=1, alias="REQUESTS_PER_MINUTE")
    max_retries: int = Field(default=3, ge=0, alias="MAX_RETRIES")
    enable_mocks: bool = Field(default=True, alias="ENABLE_MOCKS")

    warsaw_center_lat: float = 52.2297
    warsaw_center_lon: float = 21.0122

    @property
    def sqlite_path(self) -> Path:
        if self.database_url.startswith("sqlite:///"):
            return Path(self.database_url.removeprefix("sqlite:///"))
        return Path("real_estate_agents.db")

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()