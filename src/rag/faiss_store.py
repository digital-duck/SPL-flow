"""FAISS-backed RAG context store — local-dev / zero-infra fallback.

Not the default (use ChromaStore).  Useful when ChromaDB cannot be installed
or for environments that already have faiss-cpu (a spl-llm dependency).

Limitations vs ChromaStore:
  - Retrieval is keyword-level (hash bag-of-words), not semantic.
  - Metadata is stored in a JSON sidecar file, not co-located with vectors.
  - FAISS does not support in-place deletion: delete() rebuilds the index.
  - No native metadata filtering: active/user_id filters applied post-query.

Install:  pip install faiss-cpu  (already in spl-llm dependencies)
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

import numpy as np

from .store import RAGRecord, VectorStore

_DIM = 256  # embedding dimension


def _embed(text: str) -> np.ndarray:
    """Hash bag-of-words embedding — fast, zero-dependency, keyword-quality.

    Each word is hashed to a bucket; bucket counts are L2-normalised.
    Adequate for basic keyword recall; replace with a sentence-transformer
    for semantic similarity.
    """
    vec = np.zeros(_DIM, dtype=np.float32)
    for word in text.lower().split():
        bucket = int(hashlib.md5(word.encode()).hexdigest(), 16) % _DIM
        vec[bucket] += 1.0
    norm = float(np.linalg.norm(vec))
    return vec / norm if norm else vec


class FAISSStore(VectorStore):
    """FAISS + JSON sidecar store.

    Parameters
    ----------
    persist_dir : directory for index.faiss + meta.json files
    """

    DEFAULT_PERSIST_DIR = "./data/rag_faiss"

    def __init__(self, persist_dir: str = DEFAULT_PERSIST_DIR) -> None:
        try:
            import faiss  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "faiss-cpu is required for FAISSStore: pip install faiss-cpu"
            ) from exc
        self._dir = Path(persist_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._dir / "index.faiss"
        self._meta_path = self._dir / "meta.json"
        # id → serialised RAGRecord fields
        self._records: dict[str, dict] = {}
        # FAISS row index → record id  (FAISS rows are positional)
        self._id_order: list[str] = []
        self._index = self._load_index()
        self._load_meta()

    # ── write ──────────────────────────────────────────────────────────────────

    def upsert(self, record: RAGRecord) -> None:
        if record.id in self._records:
            # metadata update only — embedding stays the same (same query text)
            self._records[record.id] = self._serialize(record)
        else:
            vec = _embed(record.nl_query).reshape(1, -1)
            self._index.add(vec)
            self._id_order.append(record.id)
            self._records[record.id] = self._serialize(record)
        self._save()

    def delete(self, id: str) -> None:
        self._records.pop(id, None)
        self._id_order = [i for i in self._id_order if i != id]
        self._rebuild_index()
        self._save()

    def set_active(self, id: str, active: bool) -> None:
        if id in self._records:
            self._records[id]["active"] = active
            self._save()

    # ── read ───────────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        k: int = 5,
        *,
        user_id: str = "",
        active_only: bool = True,
    ) -> list[RAGRecord]:
        if not self._id_order:
            return []
        vec = _embed(query).reshape(1, -1)
        # over-fetch to leave room for post-query filtering
        n = min(k * 4, len(self._id_order))
        _, indices = self._index.search(vec, n)
        results: list[RAGRecord] = []
        for idx in indices[0]:
            if idx == -1 or idx >= len(self._id_order):
                continue
            id_ = self._id_order[idx]
            rec = self._deserialize(id_, self._records[id_])
            if active_only and not rec.active:
                continue
            if user_id and rec.user_id != user_id:
                continue
            results.append(rec)
            if len(results) >= k:
                break
        return results

    def get(self, id: str) -> Optional[RAGRecord]:
        if id not in self._records:
            return None
        return self._deserialize(id, self._records[id])

    def list_all(
        self,
        *,
        user_id: str = "",
        active_only: bool = False,
    ) -> list[RAGRecord]:
        records = [self._deserialize(id_, d) for id_, d in self._records.items()]
        if active_only:
            records = [r for r in records if r.active]
        if user_id:
            records = [r for r in records if r.user_id == user_id]
        records.sort(key=lambda r: r.timestamp, reverse=True)
        return records

    def count(self) -> int:
        return len(self._records)

    # ── persistence ────────────────────────────────────────────────────────────

    def _load_index(self):
        import faiss
        if self._index_path.exists() and self._index_path.stat().st_size > 0:
            return faiss.read_index(str(self._index_path))
        return faiss.IndexFlatIP(_DIM)

    def _load_meta(self) -> None:
        if self._meta_path.exists():
            data = json.loads(self._meta_path.read_text(encoding="utf-8"))
            self._records = data.get("records", {})
            self._id_order = data.get("id_order", [])

    def _save(self) -> None:
        import faiss
        self._meta_path.write_text(
            json.dumps({"records": self._records, "id_order": self._id_order}),
            encoding="utf-8",
        )
        faiss.write_index(self._index, str(self._index_path))

    def _rebuild_index(self) -> None:
        import faiss
        self._index = faiss.IndexFlatIP(_DIM)
        if self._id_order:
            vecs = np.vstack(
                [_embed(self._records[id_]["nl_query"]) for id_ in self._id_order]
            )
            self._index.add(vecs)

    # ── serialisation ──────────────────────────────────────────────────────────

    @staticmethod
    def _serialize(r: RAGRecord) -> dict:
        return {
            "nl_query": r.nl_query,
            "spl_query": r.spl_query,
            "source": r.source,
            "adapter": r.adapter,
            "spl_warnings": r.spl_warnings,
            "timestamp": r.timestamp,
            "user_id": r.user_id,
            "active": r.active,
            "metadata": r.metadata,
        }

    @staticmethod
    def _deserialize(id_: str, d: dict) -> RAGRecord:
        return RAGRecord(
            id=id_,
            nl_query=d.get("nl_query", ""),
            spl_query=d.get("spl_query", ""),
            source=d.get("source", "human"),
            adapter=d.get("adapter", ""),
            spl_warnings=d.get("spl_warnings", []),
            timestamp=d.get("timestamp", ""),
            user_id=d.get("user_id", ""),
            active=d.get("active", True),
            metadata=d.get("metadata", {}),
        )
