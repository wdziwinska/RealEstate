from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from app.models import PropertyOffer


class ChromaStore:
    """ChromaDB adapter with in-memory fallback and deterministic local embeddings."""

    def __init__(self, persist_dir: Path | str = ".chroma", collection_name: str = "offers") -> None:
        self.persist_dir = Path(persist_dir)
        self.collection_name = collection_name
        self._memory: dict[str, tuple[list[float], str, dict[str, Any]]] = {}
        self._collection: Any | None = None
        self._init_chroma()

    def _init_chroma(self) -> None:
        try:
            import chromadb

            self.persist_dir.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(self.persist_dir))
            self._collection = client.get_or_create_collection(name=self.collection_name)
        except Exception:
            self._collection = None

    def upsert_offer(self, offer: PropertyOffer) -> None:
        document = f"{offer.title}\n{offer.address}\n{offer.description}"
        embedding = embed_text(document)
        metadata = {
            "title": offer.title,
            "municipality": offer.municipality,
            "price_pln": offer.price_pln,
            "price_per_m2": offer.price_per_m2,
        }
        if self._collection is not None:
            try:
                self._collection.upsert(
                    ids=[offer.id],
                    embeddings=[embedding],
                    documents=[document],
                    metadatas=[metadata],
                )
                return
            except Exception:
                pass
        self._memory[offer.id] = (embedding, document, metadata)

    def query(self, query_text: str, limit: int = 5) -> list[dict[str, Any]]:
        query_embedding = embed_text(query_text)
        if self._collection is not None:
            try:
                result = self._collection.query(
                    query_embeddings=[query_embedding],
                    n_results=limit,
                    include=["documents", "metadatas", "distances"],
                )
                ids = result.get("ids", [[]])[0]
                documents = result.get("documents", [[]])[0]
                metadatas = result.get("metadatas", [[]])[0]
                distances = result.get("distances", [[]])[0]
                return [
                    {
                        "id": offer_id,
                        "document": document,
                        "metadata": metadata,
                        "distance": distance,
                    }
                    for offer_id, document, metadata, distance in zip(
                        ids, documents, metadatas, distances, strict=False
                    )
                ]
            except Exception:
                pass

        scored = []
        for offer_id, (embedding, document, metadata) in self._memory.items():
            scored.append(
                {
                    "id": offer_id,
                    "document": document,
                    "metadata": metadata,
                    "distance": 1 - cosine_similarity(query_embedding, embedding),
                }
            )
        return sorted(scored, key=lambda item: item["distance"])[:limit]


def embed_text(text: str, dimensions: int = 16) -> list[float]:
    vector = [0.0 for _ in range(dimensions)]
    for token in text.lower().split():
        bucket = sum(ord(char) for char in token) % dimensions
        vector[bucket] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / norm, 6) for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=False))
