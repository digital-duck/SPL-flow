"""Factory function for creating VectorStore instances.

All code outside src/rag/ should use get_store() rather than importing
a concrete store class, so the backend can be changed in one place.
"""
from .store import VectorStore


def get_store(
    backend: str = "chroma",
    **kwargs,
) -> VectorStore:
    """Return a VectorStore instance for the requested backend.

    Parameters
    ----------
    backend : "chroma" (default) | "faiss"
    **kwargs : forwarded to the store constructor

    ChromaStore kwargs
    ------------------
    persist_dir     : str  (default "./data/rag")
    collection_name : str  (default "spl_rag")
                      Set to f"spl_rag_{user_id}" for per-user isolation.

    FAISSStore kwargs
    -----------------
    persist_dir : str  (default "./data/rag_faiss")

    Examples
    --------
    store = get_store()                                       # ChromaDB default
    store = get_store("chroma", collection_name="spl_rag_alice")  # per-user
    store = get_store("faiss",  persist_dir="/tmp/rag")           # FAISS fallback
    """
    if backend == "chroma":
        from .chroma_store import ChromaStore
        return ChromaStore(**kwargs)
    if backend == "faiss":
        from .faiss_store import FAISSStore
        return FAISSStore(**kwargs)
    raise ValueError(
        f"Unknown RAG backend: {backend!r}. Valid options: 'chroma', 'faiss'."
    )
