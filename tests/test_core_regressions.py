import unittest
from pathlib import Path
from unittest.mock import patch

from src.ingestion.repo_indexer import RepoIndexer
from src.rag.chroma_store import RAGStore
from src.tools.tool_registry import ToolRegistry, _validate_dockerfile


class FakeCollection:
    def __init__(self):
        self.where = None

    def query(self, **kwargs):
        self.where = kwargs["where"]
        return {
            "ids": [["chunk"]],
            "metadatas": [[{"file_path": "app.py", "language": "python", "start_line": 1, "end_line": 1}]],
            "documents": [["print('ok')"]],
            "distances": [[0.0]],
        }


class FakeEmbeddingCollection(FakeCollection):
    """Stand-in Chroma collection with metadata and upsert support."""

    def __init__(self, metadata=None):
        super().__init__()
        self.metadata = dict(metadata or {})
        self.upserts = []

    def count(self):
        return len(self.upserts)

    def modify(self, **kwargs):
        if "metadata" in kwargs:
            self.metadata = dict(kwargs["metadata"])

    def upsert(self, **kwargs):
        self.upserts.append(kwargs)


class CoreRegressionTests(unittest.TestCase):
    def test_chunker_does_not_emit_a_wholly_overlapping_final_chunk(self):
        source = Path(__file__)
        line_count = len(source.read_text(encoding="utf-8").splitlines())
        chunks = RepoIndexer(source.parent.parent, chunk_size=30, chunk_overlap=10).chunk_file(source)
        self.assertEqual(chunks[-1].end_line, line_count)
        self.assertTrue(all(a.end_line < b.end_line for a, b in zip(chunks, chunks[1:])))

    def test_rag_rebuilds_index_when_embedding_dimension_changes(self):
        """plan.md Phase 4: a different embedding dimension must not reuse the index."""
        store = RAGStore()
        store._collection = FakeEmbeddingCollection(
            {
                "hnsw:space": "cosine",
                "embedding_model": "all-MiniLM-L6-v2",
                "embedding_dimensions": 384,
            }
        )
        store._indexed_count = 5

        with patch.object(RAGStore, "reset") as reset:
            rebuilt = store.ensure_embedding_compatibility(embedding_dimensions=768)

        self.assertTrue(rebuilt)
        reset.assert_called_once()

    def test_rag_reuses_index_for_a_matching_embedding_signature(self):
        store = RAGStore()
        store._collection = FakeEmbeddingCollection(
            {
                "hnsw:space": "cosine",
                "embedding_model": "all-MiniLM-L6-v2",
                "embedding_dimensions": 384,
            }
        )

        with patch.object(RAGStore, "reset") as reset:
            rebuilt = store.ensure_embedding_compatibility(
                embedding_model="all-MiniLM-L6-v2",
                embedding_dimensions=384,
            )

        self.assertFalse(rebuilt)
        reset.assert_not_called()

    def test_rag_records_embedding_signature_while_indexing(self):
        from src.ingestion.repo_indexer import CodeChunk

        store = RAGStore()
        store._collection = FakeEmbeddingCollection()
        chunk = CodeChunk(
            file_path="app.py",
            language="python",
            start_line=1,
            end_line=2,
            content="print('hi')",
        )

        indexed = store.index_chunks(
            [chunk],
            lambda documents: [[0.0] * 384 for _ in documents],
            embedding_model="all-MiniLM-L6-v2",
        )

        self.assertEqual(indexed, 1)
        self.assertEqual(store._collection.metadata.get("embedding_model"), "all-MiniLM-L6-v2")
        self.assertEqual(store._collection.metadata.get("embedding_dimensions"), 384)
        self.assertEqual(store.embedding_signature()["embedding_dimensions"], 384)

    def test_rag_combines_language_and_file_filters(self):
        store = RAGStore()
        store._collection = FakeCollection()
        store._indexed_count = 1
        store.query("test", lambda _: [[0.1]], filter_language="python", filter_file="app.py")
        self.assertEqual(
            store._collection.where,
            {"$and": [{"language": "python"}, {"file_path": "app.py"}]},
        )

    def test_read_file_cannot_escape_repository(self):
        repo = Path(__file__).parent.parent
        result = ToolRegistry(str(repo)).invoke("read_file", file_path="../secret.txt")
        self.assertFalse(result.success)
        self.assertEqual(result.error, "path traversal blocked")

    def test_dockerfile_add_is_reported(self):
        class Dockerfile:
            def read_text(self, **kwargs):
                return "FROM python:3.12\nADD app /app\n"

            def relative_to(self, repo):
                return Path("Dockerfile")

        with patch("src.tools.tool_registry.Path.rglob", return_value=[Dockerfile()]):
            result = _validate_dockerfile("repo")
        checks = result.details[0]["checks"]
        self.assertTrue(any(c["check"] == "uses_copy_not_add" and c["status"] == "warning" for c in checks))


if __name__ == "__main__":
    unittest.main()
