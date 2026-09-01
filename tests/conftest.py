from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from core.config import Config
from core.document_parser import DocumentParser
from core.metadata_manager import MetadataManager
from core.text_splitter import KnowledgeTextSplitter
from core.vector_store import VectorStore


class FakeEmbedder:
    def __init__(self, dimension: int = 8):
        self.model = "fake-embedder"
        self.batch_size = 32
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def is_available(self) -> bool:
        return True

    def is_model_available(self) -> bool:
        return True

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def embed_query(self, query: str) -> list[float]:
        return self._embed_one(query)

    def _embed_one(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        vals = [((digest[i % len(digest)] / 255.0) * 2 - 1) for i in range(self._dimension)]
        norm = sum(v * v for v in vals) ** 0.5 or 1.0
        return [v / norm for v in vals]


@pytest.fixture
def tmp_config(tmp_path: Path) -> Config:
    cfg = Config(
        files_dir=tmp_path / "files",
        chroma_dir=tmp_path / "chroma_db",
        sqlite_path=tmp_path / "kb.sqlite",
        logs_dir=tmp_path / "logs",
        chunk_size=200,
        chunk_overlap=20,
        embedding_model="fake-embedder",
        top_k=5,
        similarity_threshold=0.0,
    )
    cfg.files_dir.mkdir(parents=True, exist_ok=True)
    cfg.chroma_dir.mkdir(parents=True, exist_ok=True)
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    return cfg


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def vector_store(tmp_config: Config) -> VectorStore:
    return VectorStore(str(tmp_config.chroma_dir))


@pytest.fixture
def metadata(tmp_config: Config, vector_store: VectorStore) -> MetadataManager:
    return MetadataManager(str(tmp_config.sqlite_path), vector_store=vector_store)


@pytest.fixture
def parser() -> DocumentParser:
    return DocumentParser()


@pytest.fixture
def splitter(tmp_config: Config) -> KnowledgeTextSplitter:
    return KnowledgeTextSplitter(
        chunk_size=tmp_config.chunk_size,
        chunk_overlap=tmp_config.chunk_overlap,
    )


@pytest.fixture
def sample_txt(tmp_path: Path) -> Path:
    path = tmp_path / "sample.txt"
    path.write_text(
        "AI is a branch of computer science.\n\n"
        "Machine learning is a core technique.\n\n"
        "Deep learning uses neural networks.",
        encoding="utf-8",
    )
    return path
