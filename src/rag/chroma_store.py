"""
ChromaDB RAG Store — vector database for code snippet retrieval.

Uses ROCm GPU embeddings via sentence-transformers for indexing and querying.
Provides top-k semantic search with file:line references.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class RAGStore:
    """
    ChromaDB-backed vector store for code chunks.

    Usage:
        store = RAGStore(persist_dir="./chroma_db")
        store.index_chunks(chunks, embed_fn)
        results = store.query("SQL injection vulnerability", embed_fn, k=5)
    """

    def __init__(self, persist_dir: str = "./chroma_db", collection_name: str = "code_chunks") -> None:
        self.persist_dir = Path(persist_dir)
        self.collection_name = collection_name
        self._client: Any = None
        self._collection: Any = None
        self._indexed_count: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Create or load the ChromaDB collection."""
        try:
            import chromadb
            from chromadb.config import Settings

            self.persist_dir.mkdir(parents=True, exist_ok=True)

            self._client = chromadb.PersistentClient(
                path=str(self.persist_dir),
                settings=Settings(anonymized_telemetry=False),
            )

            # Get or create collection
            try:
                self._collection = self._client.get_collection(self.collection_name)
                self._indexed_count = self._collection.count()
                logger.info(
                    "Loaded existing collection '%s' with %d documents.",
                    self.collection_name,
                    self._indexed_count,
                )
            except Exception:
                self._collection = self._client.create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
                logger.info("Created new collection '%s'.", self.collection_name)

        except ImportError:
            logger.error("chromadb not installed. RAG will be unavailable.")
            self._collection = None
        except Exception as exc:
            logger.error("Failed to initialize ChromaDB: %s", exc)
            self._collection = None

    def reset(self) -> None:
        """Delete and recreate the collection."""
        if self._client is not None:
            try:
                self._client.delete_collection(self.collection_name)
            except Exception:
                pass
            self._collection = self._client.create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            self._indexed_count = 0
            logger.info("Collection '%s' reset.", self.collection_name)

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def index_chunks(
        self,
        chunks: list[Any],  # list[CodeChunk]
        embed_fn: Any,  # callable: list[str] -> list[list[float]]
        *,
        batch_size: int = 64,
    ) -> int:
        """
        Embed and index a list of CodeChunks into ChromaDB.

        Args:
            chunks: List of CodeChunk objects (from repo_indexer).
            embed_fn: Function that takes list[str] and returns list[list[float]].
            batch_size: Number of chunks to embed per batch.

        Returns:
            Number of chunks indexed.
        """
        if self._collection is None:
            self.initialize()
        if self._collection is None:
            return 0

        if not chunks:
            return 0

        total = 0
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            documents = [c.to_document() for c in batch]
            ids = [c.chunk_id for c in batch]
            metadatas = [
                {
                    "file_path": c.file_path,
                    "language": c.language,
                    "start_line": c.start_line,
                    "end_line": c.end_line,
                }
                for c in batch
            ]

            embeddings = embed_fn(documents)

            self._collection.add(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
            )
            total += len(batch)
            logger.debug("Indexed batch %d/%d", total, len(chunks))

        self._indexed_count = self._collection.count()
        logger.info("Indexed %d chunks total. Collection size: %d", total, self._indexed_count)
        return total

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def query(
        self,
        query_text: str,
        embed_fn: Any,
        *,
        k: int = 5,
        filter_language: Optional[str] = None,
        filter_file: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve top-k most relevant code chunks for a query.

        Returns list of dicts with keys: id, file_path, language, start_line,
        end_line, content (reconstructed), score.
        """
        if self._collection is None:
            self.initialize()
        if self._collection is None or self._indexed_count == 0:
            return []

        query_embedding = embed_fn([query_text])[0]

        where_filter: Optional[dict] = None
        if filter_language:
            where_filter = {"language": filter_language}
        if filter_file:
            where_filter = {"file_path": filter_file}

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(k, self._indexed_count),
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )

        formatted: list[dict[str, Any]] = []
        if not results["ids"] or not results["ids"][0]:
            return formatted

        for i, doc_id in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            doc = results["documents"][0][i] if results["documents"] else ""
            distance = results["distances"][0][i] if results["distances"] else 0.0

            # Cosine distance → similarity score
            similarity = 1.0 - distance if distance else 1.0

            formatted.append(
                {
                    "id": doc_id,
                    "file_path": meta.get("file_path", ""),
                    "language": meta.get("language", ""),
                    "start_line": meta.get("start_line", 0),
                    "end_line": meta.get("end_line", 0),
                    "content": doc,
                    "score": round(similarity, 4),
                }
            )

        return formatted

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def count(self) -> int:
        return self._indexed_count

    @property
    def is_ready(self) -> bool:
        return self._collection is not None and self._indexed_count > 0
