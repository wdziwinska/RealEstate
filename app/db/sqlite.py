from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from app.models import GraphState, PropertyOffer


class SQLiteStore:
    """SQLite persistence for workflow snapshots and discovered offers."""

    def __init__(self, db_path: Path | str = "real_estate_agents.db") -> None:
        self.db_path = Path(db_path)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS state_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS offers (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    municipality TEXT NOT NULL,
                    price_pln INTEGER NOT NULL,
                    price_per_m2 REAL NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def save_state(self, state: GraphState) -> int:
        payload = state.model_dump_json()
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO state_snapshots(created_at, status, payload) VALUES (?, ?, ?)",
                (now, state.status.value, payload),
            )
            for offer in state.offers:
                self.upsert_offer(offer, connection=connection)
            return int(cursor.lastrowid)

    def load_latest_state(self) -> GraphState | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload FROM state_snapshots ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return GraphState.model_validate_json(row["payload"])

    def upsert_offer(
        self,
        offer: PropertyOffer,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        payload = offer.model_dump_json()
        now = datetime.now(timezone.utc).isoformat()
        params = (
            offer.id,
            offer.title,
            offer.municipality,
            offer.price_pln,
            offer.price_per_m2,
            payload,
            now,
        )
        query = """
            INSERT INTO offers(id, title, municipality, price_pln, price_per_m2, payload, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,
                municipality=excluded.municipality,
                price_pln=excluded.price_pln,
                price_per_m2=excluded.price_per_m2,
                payload=excluded.payload,
                updated_at=excluded.updated_at
        """
        if connection is not None:
            connection.execute(query, params)
            return
        with self.connect() as own_connection:
            own_connection.execute(query, params)

    def list_offers(self) -> list[PropertyOffer]:
        with self.connect() as connection:
            rows = connection.execute("SELECT payload FROM offers ORDER BY updated_at DESC").fetchall()
        return [PropertyOffer.model_validate_json(row["payload"]) for row in rows]

    def export_json(self) -> dict[str, object]:
        state = self.load_latest_state()
        return {
            "latest_state": json.loads(state.model_dump_json()) if state else None,
            "offers": [json.loads(offer.model_dump_json()) for offer in self.list_offers()],
        }
