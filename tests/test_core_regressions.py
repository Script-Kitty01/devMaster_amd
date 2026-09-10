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


class CoreRegressionTests(unittest.TestCase):
    def test_chunker_does_not_emit_a_wholly_overlapping_final_chunk(self):
        source = Path(__file__)
        line_count = len(source.read_text(encoding="utf-8").splitlines())
        chunks = RepoIndexer(source.parent.parent, chunk_size=30, chunk_overlap=10).chunk_file(source)
        self.assertEqual(chunks[-1].end_line, line_count)
        self.assertTrue(all(a.end_line < b.end_line for a, b in zip(chunks, chunks[1:])))

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
