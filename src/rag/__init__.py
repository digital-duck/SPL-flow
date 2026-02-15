"""SPL-Flow RAG context store — public interface.

Usage
-----
from src.rag import get_store, RAGRecord

store = get_store()                      # ChromaDB, default path
store = get_store("chroma", collection_name="spl_rag_alice")  # per-user
store = get_store("faiss")               # FAISS fallback
"""
from .store import RAGRecord, VectorStore
from .factory import get_store

__all__ = ["RAGRecord", "VectorStore", "get_store"]
