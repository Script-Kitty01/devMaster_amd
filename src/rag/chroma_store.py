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
        store.index_chunks(chunks, embed_fn, embedding_model="all-MiniLM-L6-v2")
        results = store.query("SQL injection vulnerability", embed_fn, k=5)
    """

    # Collection metadata keys that pin an index to its embedding signature.
    # plan.md Phase 4: an index built with another model or dimension must be
    # rebuilt, never reused.
    EMBEDDING_MODEL_KEY = "embedding_model"
    EMBEDDING_DIMENSIONS_KEY = "embedding_dimensions"

    def __init__(self, persist_dir: str = "./chroma_db", collection_name: str = "code_chunks") -> None:
        self.persist_dir = Path(persist_dir)
        self.collection_name = collection_name
        self._client: Any = None
        self._collection: Any = None
        self._indexed_count: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(
        self,
        *,
        embedding_model: str = "",
        embedding_dimensions: int = 0,
    ) -> None:
        """Create or load the ChromaDB collection.

        When an embedding signature is supplied, it is compared with the
        signature recorded in the collection metadata; a mismatch resets the
        index so a stale model/dimension is never reused (plan.md Phase 4).
        """
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
                self.ensure_embedding_compatibility(
                    embedding_model=embedding_model,
                    embedding_dimensions=embedding_dimensions,
                )
            except Exception:
                self._collection = self._client.create_collection(
                    name=self.collection_name,
                    metadata=self._embedding_metadata(embedding_model, embedding_dimensions),
                )
                logger.info("Created new collection '%s'.", self.collection_name)

        except ImportError:
            logger.error("chromadb not installed. RAG will be unavailable.")
            self._collection = None
        except Exception as exc:
            logger.error("Failed to initialize ChromaDB: %s", exc)
            self._collection = None

    def reset(self, *, embedding_model: str = "", embedding_dimensions: int = 0) -> None:
        """Delete and recreate the collection, re-stamping the embedding signature."""
        if self._client is not None:
            try:
                self._client.delete_collection(self.collection_name)
            except Exception:
                pass
            self._collection = self._client.create_collection(
                name=self.collection_name,
                metadata=self._embedding_metadata(embedding_model, embedding_dimensions),
            )
            self._indexed_count = 0
            logger.info("Collection '%s' reset.", self.collection_name)

    # ------------------------------------------------------------------
    # Embedding signature (plan.md Phase 4 item 4)
    # ------------------------------------------------------------------

    def _embedding_metadata(self, embedding_model: str, embedding_dimensions: int) -> dict[str, Any]:
        """Collection metadata describing the embedding model that built the index."""
        metadata: dict[str, Any] = {"hnsw:space": "cosine"}
        if embedding_model:
            metadata[self.EMBEDDING_MODEL_KEY] = embedding_model
        if embedding_dimensions:
            metadata[self.EMBEDDING_DIMENSIONS_KEY] = int(embedding_dimensions)
        return metadata

    def embedding_signature(self) -> dict[str, Any]:
        """Return the embedding model/dimensions recorded for the open index."""
        if self._collection is None:
            return {self.EMBEDDING_MODEL_KEY: "", self.EMBEDDING_DIMENSIONS_KEY: 0}
        metadata = dict(self._collection.metadata or {})
        return {
            self.EMBEDDING_MODEL_KEY: metadata.get(self.EMBEDDING_MODEL_KEY, ""),
            self.EMBEDDING_DIMENSIONS_KEY: metadata.get(self.EMBEDDING_DIMENSIONS_KEY, 0),
        }

    def ensure_embedding_compatibility(
        self,
        *,
        embedding_model: str = "",
        embedding_dimensions: int = 0,
    ) -> bool:
        """Rebuild the index when the embedding model or dimension changed.

        Only explicitly supplied values are compared, so a caller that knows
        nothing about embeddings keeps the previous behaviour.  Returns True
        when the collection was reset.
        """
        if self._collection is None:
            return False

        metadata = dict(self._collection.metadata or {})
        stored_model = str(metadata.get(self.EMBEDDING_MODEL_KEY) or "")
        stored_dimensions = metadata.get(self.EMBEDDING_DIMENSIONS_KEY)

        model_changed = bool(embedding_model) and bool(stored_model) and stored_model != embedding_model
        dimensions_changed = False
        if embedding_dimensions and stored_dimensions not in (None, ""):
            try:
                dimensions_changed = int(stored_dimensions) != int(embedding_dimensions)
            except (TypeError, ValueError):
                dimensions_changed = True

        if not (model_changed or dimensions_changed):
            return False

        rebuilt_dimensions = int(embedding_dimensions) if embedding_dimensions else 0
        if not rebuilt_dimensions and stored_dimensions not in (None, ""):
            try:
                rebuilt_dimensions = int(stored_dimensions)
            except (TypeError, ValueError):
                rebuilt_dimensions = 0

        logger.warning(
            "Embedding signature changed (model %r -> %r, dimensions %s -> %s); rebuilding index '%s'.",
            stored_model or "unknown",
            embedding_model or stored_model or "unknown",
            stored_dimensions if stored_dimensions not in (None, "") else "unknown",
            embedding_dimensions or "unknown",
            self.collection_name,
        )
        self.reset(
            embedding_model=embedding_model or stored_model,
            embedding_dimensions=rebuilt_dimensions,
        )
        return True

    def _record_embedding_metadata(
        self,
        *,
        embedding_model: str,
        embedding_dimensions: int,
    ) -> None:
        """Stamp the embedding signature onto the collection for later checks."""
        if self._collection is None or not (embedding_model or embedding_dimensions):
            return

        metadata = dict(self._collection.metadata or {})
        metadata.setdefault("hnsw:space", "cosine")
        if embedding_model:
            metadata[self.EMBEDDING_MODEL_KEY] = embedding_model
        if embedding_dimensions:
            metadata[self.EMBEDDING_DIMENSIONS_KEY] = int(embedding_dimensions)

        try:
            self._collection.modify(metadata=metadata)
        except Exception as exc:  # noqa: BLE001 - metadata recording is best effort
            logger.debug("Could not record embedding metadata: %s", exc)

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def index_chunks(
        self,
        chunks: list[Any],  # list[CodeChunk]
        embed_fn: Any,  # callable: list[str] -> list[list[float]]
        *,
        embedding_model: str = "",
        batch_size: int = 64,
    ) -> int:
        """
        Embed and index a list of CodeChunks into ChromaDB.

        Args:
            chunks: List of CodeChunk objects (from repo_indexer).
            embed_fn: Function that takes list[str] and returns list[list[float]].
            embedding_model: Embedding model name, recorded on the collection so a
                later run can detect that the index must be rebuilt (plan.md Phase 4).
            batch_size: Number of chunks to embed per batch.

        Returns:
            Number of chunks indexed.
        """
        if self._collection is None:
            self.initialize(embedding_model=embedding_model)
        if self._collection is None:
            return 0

        if not chunks:
            return 0

        if embedding_model:
            self.ensure_embedding_compatibility(embedding_model=embedding_model)

        total = 0
        dimensions_recorded = False
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

            # Verify the true embedding dimension before the first write: an index
            # built for another dimension must be rebuilt, never appended to.
            if not dimensions_recorded and embeddings:
                dimensions = len(embeddings[0])
                self.ensure_embedding_compatibility(
                    embedding_model=embedding_model,
                    embedding_dimensions=dimensions,
                )
                self._record_embedding_metadata(
                    embedding_model=embedding_model,
                    embedding_dimensions=dimensions,
                )
                dimensions_recorded = True

            # Re-indexing an unchanged repository is expected.  Upsert keeps
            # stable chunk IDs from causing a duplicate-ID failure.
            self._collection.upsert(
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

        filters: list[dict[str, str]] = []
        if filter_language:
            filters.append({"language": filter_language})
        if filter_file:
            filters.append({"file_path": filter_file})
        where_filter: Optional[dict] = None
        if len(filters) == 1:
            where_filter = filters[0]
        elif filters:
            where_filter = {"$and": filters}

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
