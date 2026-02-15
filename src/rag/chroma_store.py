"""ChromaDB-backed RAG context store — default backend.

ChromaDB is chosen as the default because:
  - Metadata (source, user_id, active, timestamp) is stored and filterable
    natively alongside the vectors — no separate metadata table needed.
  - Per-user isolation via collection_name (one collection per user enables
    the digital-twin personalisation roadmap).
  - Persistent by default: data survives process restarts automatically.
  - `active` filtering is a single where-clause — human-review deactivations
    are immediately reflected in retrieval without rebuilding an index.

Install:  pip install chromadb
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import chromadb

from .store import RAGRecord, VectorStore

# Metadata keys we own — everything else goes into RAGRecord.metadata
_OWNED_KEYS = frozenset(
    {"spl_query", "source", "adapter", "spl_warnings", "timestamp", "user_id", "active"}
)


class ChromaStore(VectorStore):
    """Persistent ChromaDB-backed store.

    Parameters
    ----------
    persist_dir : str
        Directory where ChromaDB writes its SQLite + HNSW files.
        Created automatically if it does not exist.
    collection_name : str
        Logical namespace.  Use per-user names to enable digital-twin
        personalisation:  ChromaStore(collection_name=f"spl_rag_{user_id}")
    """

    DEFAULT_PERSIST_DIR = "./data/rag"
    DEFAULT_COLLECTION = "spl_rag"

    def __init__(
        self,
        persist_dir: str = DEFAULT_PERSIST_DIR,
        collection_name: str = DEFAULT_COLLECTION,
    ) -> None:
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._col = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    # ── write ──────────────────────────────────────────────────────────────────

    def upsert(self, record: RAGRecord) -> None:
        """Insert or update by record.id (upsert semantics)."""
        self._col.upsert(
            ids=[record.id],
            documents=[record.nl_query],   # embedded text
            metadatas=[self._to_meta(record)],
        )

    def delete(self, id: str) -> None:
        """Hard-delete a record permanently."""
        self._col.delete(ids=[id])

    def set_active(self, id: str, active: bool) -> None:
        """Soft-delete (active=False) or restore (active=True).

        ChromaDB update() merges — only the `active` field is touched.
        """
        self._col.update(ids=[id], metadatas=[{"active": active}])

    # ── read ───────────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        k: int = 5,
        *,
        user_id: str = "",
        active_only: bool = True,
    ) -> list[RAGRecord]:
        total = self._col.count()
        if total == 0:
            return []
        where = self._build_where(active_only=active_only, user_id=user_id)
        kwargs: dict = {
            "query_texts": [query],
            "n_results": min(k, total),
            "include": ["documents", "metadatas"],
        }
        if where:
            kwargs["where"] = where
        try:
            results = self._col.query(**kwargs)
        except Exception:
            return []
        return [
            self._from_row(
                results["ids"][0][i],
                results["documents"][0][i],
                results["metadatas"][0][i],
            )
            for i in range(len(results["ids"][0]))
        ]

    def get(self, id: str) -> Optional[RAGRecord]:
        r = self._col.get(ids=[id], include=["documents", "metadatas"])
        if not r["ids"]:
            return None
        return self._from_row(r["ids"][0], r["documents"][0], r["metadatas"][0])

    def list_all(
        self,
        *,
        user_id: str = "",
        active_only: bool = False,
    ) -> list[RAGRecord]:
        where = self._build_where(active_only=active_only, user_id=user_id)
        kwargs: dict = {"include": ["documents", "metadatas"]}
        if where:
            kwargs["where"] = where
        try:
            r = self._col.get(**kwargs)
        except Exception:
            return []
        records = [
            self._from_row(r["ids"][i], r["documents"][i], r["metadatas"][i])
            for i in range(len(r["ids"]))
        ]
        # newest first
        records.sort(key=lambda rec: rec.timestamp, reverse=True)
        return records

    def count(self) -> int:
        return self._col.count()

    # ── helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _to_meta(record: RAGRecord) -> dict:
        return {
            "spl_query": record.spl_query,
            "source": record.source,
            "adapter": record.adapter,
            "spl_warnings": json.dumps(record.spl_warnings),
            "timestamp": record.timestamp,
            "user_id": record.user_id,
            "active": record.active,
            **record.metadata,
        }

    @staticmethod
    def _from_row(id: str, document: str, meta: dict) -> RAGRecord:
        return RAGRecord(
            id=id,
            nl_query=document,
            spl_query=meta.get("spl_query", ""),
            source=meta.get("source", "human"),
            adapter=meta.get("adapter", ""),
            spl_warnings=json.loads(meta.get("spl_warnings", "[]")),
            timestamp=meta.get("timestamp", ""),
            user_id=meta.get("user_id", ""),
            active=bool(meta.get("active", True)),
            metadata={k: v for k, v in meta.items() if k not in _OWNED_KEYS},
        )

    @staticmethod
    def _build_where(active_only: bool, user_id: str) -> dict | None:
        """Build a ChromaDB where-clause from the active and user_id filters."""
        conditions = []
        if active_only:
            conditions.append({"active": {"$eq": True}})
        if user_id:
            conditions.append({"user_id": {"$eq": user_id}})
        if not conditions:
            return None
        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}
