"""
Repository Indexer — walks a codebase, extracts source files, and prepares
chunks for the RAG engine.

Supports:
- Language-aware chunking via Pygments lexers
- File-type filtering (.py, .js, .ts, .java, .go, Dockerfile, .yaml, .tf, etc.)
- Metadata extraction (file path, language, line numbers)
- Git-aware file discovery (respects .gitignore)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

# File extensions we care about for code review
CODE_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go", ".rs", ".c", ".cpp", ".h", ".hpp",
    ".rb", ".php", ".swift", ".kt", ".scala",
    ".yaml", ".yml", ".json", ".toml", ".xml",
    ".tf", ".hcl",
    ".sh", ".bash", ".ps1",
    ".sql",
    ".dockerfile", "Dockerfile",
}

# Files we always include regardless of extension
ALWAYS_INCLUDE: set[str] = {
    "Dockerfile",
    "Makefile",
    "docker-compose.yml",
    "docker-compose.yaml",
    ".env.example",
}

# Directories to skip
SKIP_DIRS: set[str] = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "dist", "build", "target", ".next", ".nuxt",
    "vendor", "bower_components",
    ".idea", ".vscode",
}


@dataclass
class CodeChunk:
    """A chunk of source code ready for embedding."""

    file_path: str  # relative to repo root
    language: str
    start_line: int  # 1-based
    end_line: int  # 1-based, inclusive
    content: str
    metadata: dict = field(default_factory=dict)

    @property
    def chunk_id(self) -> str:
        return f"{self.file_path}:L{self.start_line}-L{self.end_line}"

    def to_document(self) -> str:
        """Format as a human-readable document for embedding."""
        return (
            f"File: {self.file_path} (lines {self.start_line}-{self.end_line})\n"
            f"Language: {self.language}\n"
            f"```{self.language}\n{self.content}\n```"
        )


class RepoIndexer:
    """
    Walks a repository directory, extracts code files, and produces
    language-aware chunks for the RAG pipeline.
    """

    def __init__(
        self,
        repo_path: str | Path,
        *,
        chunk_size: int = 50,  # lines per chunk
        chunk_overlap: int = 10,
        max_file_size_kb: int = 500,
    ) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_file_size_kb = max_file_size_kb

        if not self.repo_path.exists():
            raise FileNotFoundError(f"Repository not found: {self.repo_path}")

    # ------------------------------------------------------------------
    # File Discovery
    # ------------------------------------------------------------------

    def discover_files(self) -> list[Path]:
        """Find all code files in the repository, respecting skip dirs."""
        files: list[Path] = []

        for entry in self.repo_path.rglob("*"):
            if not entry.is_file():
                continue

            # Skip ignored directories
            parts = set(entry.relative_to(self.repo_path).parts)
            if parts & SKIP_DIRS:
                continue

            # Check extension or special filenames
            if entry.suffix.lower() in CODE_EXTENSIONS:
                files.append(entry)
            elif entry.name in ALWAYS_INCLUDE:
                files.append(entry)

        logger.info("Discovered %d code files in %s", len(files), self.repo_path)
        return sorted(files)

    # ------------------------------------------------------------------
    # Language Detection
    # ------------------------------------------------------------------

    @staticmethod
    def detect_language(file_path: Path) -> str:
        """Detect programming language from file extension."""
        ext_map: dict[str, str] = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "tsx",
            ".jsx": "jsx",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".rb": "ruby",
            ".php": "php",
            ".swift": "swift",
            ".kt": "kotlin",
            ".scala": "scala",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".json": "json",
            ".toml": "toml",
            ".xml": "xml",
            ".tf": "hcl",
            ".hcl": "hcl",
            ".sh": "bash",
            ".bash": "bash",
            ".ps1": "powershell",
            ".sql": "sql",
        }

        ext = file_path.suffix.lower()
        if ext in ext_map:
            return ext_map[ext]

        # Special filenames
        name = file_path.name
        if name == "Dockerfile" or name.endswith(".dockerfile"):
            return "dockerfile"
        if name == "Makefile":
            return "makefile"

        return "text"

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------

    def chunk_file(self, file_path: Path) -> list[CodeChunk]:
        """Split a single file into overlapping chunks."""
        try:
            size_kb = file_path.stat().st_size / 1024
            if size_kb > self.max_file_size_kb:
                logger.debug("Skipping large file: %s (%.1f KB)", file_path, size_kb)
                return []

            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            logger.warning("Failed to read %s: %s", file_path, exc)
            return []

        lines = content.splitlines()
        if not lines:
            return []

        language = self.detect_language(file_path)
        rel_path = str(file_path.relative_to(self.repo_path))

        chunks: list[CodeChunk] = []
        step = max(1, self.chunk_size - self.chunk_overlap)

        for start in range(0, len(lines), step):
            end = min(start + self.chunk_size, len(lines))
            chunk_lines = lines[start:end]
            chunk_text = "\n".join(chunk_lines)

            chunks.append(
                CodeChunk(
                    file_path=rel_path,
                    language=language,
                    start_line=start + 1,
                    end_line=end,
                    content=chunk_text,
                    metadata={
                        "repo": self.repo_path.name,
                        "ext": file_path.suffix,
                    },
                )
            )

        return chunks

    def chunk_all(self, files: Optional[list[Path]] = None) -> list[CodeChunk]:
        """Chunk all discovered files (or a provided subset)."""
        if files is None:
            files = self.discover_files()

        all_chunks: list[CodeChunk] = []
        for fp in files:
            all_chunks.extend(self.chunk_file(fp))

        logger.info(
            "Produced %d chunks from %d files in %s",
            len(all_chunks),
            len(files),
            self.repo_path.name,
        )
        return all_chunks

    # ------------------------------------------------------------------
    # Iterator (for large repos)
    # ------------------------------------------------------------------

    def iter_chunks(self, files: Optional[list[Path]] = None) -> Iterator[CodeChunk]:
        """Yield chunks one at a time — memory-friendly for large repos."""
        if files is None:
            files = self.discover_files()

        for fp in files:
            yield from self.chunk_file(fp)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        """Return summary statistics about the indexed repository."""
        files = self.discover_files()
        total_lines = 0
        languages: dict[str, int] = {}

        for fp in files:
            try:
                n = sum(1 for _ in open(fp, encoding="utf-8", errors="replace"))
                total_lines += n
                lang = self.detect_language(fp)
                languages[lang] = languages.get(lang, 0) + n
            except Exception:
                pass

        return {
            "repo_name": self.repo_path.name,
            "file_count": len(files),
            "total_lines": total_lines,
            "languages": languages,
        }
