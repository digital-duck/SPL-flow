"""Abstract vector store interface and RAGRecord data type.

Every backend (ChromaDB, FAISS, …) implements VectorStore so the rest of the
codebase never imports a concrete store class directly — only get_store().
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RAGRecord:
    """A single (NL query, SPL) pair stored in the RAG context store.

    Data quality tiers (stored in `source`):
        "human"     — captured from a real user session; gold standard
        "edited"    — user manually corrected the generated SPL; gold+
        "synthetic" — generated offline by a data-gen script; silver

    `active=False` is a soft-delete: the record is excluded from retrieval
    but not removed from the store.  Human-in-the-loop review in the
    Streamlit UI sets this flag.
    """
    id: str                                             # deterministic hash of nl_query
    nl_query: str                                       # original user input
    spl_query: str                                      # validated SPL output
    source: str = "human"                               # "human" | "edited" | "synthetic"
    adapter: str = ""                                   # LLM adapter used at capture time
    spl_warnings: list[str] = field(default_factory=list)
    timestamp: str = ""                                 # ISO-8601 UTC
    user_id: str = ""                                   # "" = single-user mode
    active: bool = True                                 # False = excluded from retrieval
    metadata: dict = field(default_factory=dict)        # extensible: domain, tags, score, …


class VectorStore(ABC):
    """Abstract interface for the SPL RAG context store.

    Concrete implementations live in chroma_store.py and faiss_store.py.
    Use get_store(backend) to obtain an instance — never import a concrete
    class directly so the backend can be swapped without touching call sites.
    """

    @abstractmethod
    def upsert(self, record: RAGRecord) -> None:
        """Insert or update a record (keyed by record.id)."""

    @abstractmethod
    def search(
        self,
        query: str,
        k: int = 5,
        *,
        user_id: str = "",
        active_only: bool = True,
    ) -> list[RAGRecord]:
        """Return the k most semantically similar records.

        Only active records are returned when active_only=True (default).
        Scope to a single user by passing user_id.
        """

    @abstractmethod
    def get(self, id: str) -> Optional[RAGRecord]:
        """Return a record by ID, or None if not found."""

    @abstractmethod
    def delete(self, id: str) -> None:
        """Hard-delete a record (permanent)."""

    @abstractmethod
    def set_active(self, id: str, active: bool) -> None:
        """Soft-delete (active=False) or restore (active=True) a record.

        Prefer this over delete() — inactive records can be restored and
        provide a useful audit trail of what was reviewed and rejected.
        """

    @abstractmethod
    def list_all(
        self,
        *,
        user_id: str = "",
        active_only: bool = False,
    ) -> list[RAGRecord]:
        """Return all records, newest first.

        active_only=False (default) returns both active and inactive records,
        which is what the human-review UI needs.
        """

    @abstractmethod
    def count(self) -> int:
        """Total number of records (active + inactive)."""
