from __future__ import annotations

from core.bm25_retriever import BM25Retriever
from core.metadata_manager import MetadataManager
from core.vector_store import VectorStore
from tests.conftest import FakeEmbedder


def test_jieba_available_check():
    result = BM25Retriever.is_jieba_available()
    assert isinstance(result, bool)


def test_bm25_empty_index(tmp_path):
    db_path = tmp_path / "kb.sqlite"
    meta = MetadataManager(str(db_path))
    bm25 = BM25Retriever(meta)
    bm25.build_index()
    results = bm25.search("test query", top_k=5)
    assert results == []


def test_bm25_search(tmp_path):
    from core.config import Config
    cfg = Config(
        files_dir=tmp_path / "files",
        chroma_dir=tmp_path / "chroma_db",
        sqlite_path=tmp_path / "kb.sqlite",
        logs_dir=tmp_path / "logs",
    )
    cfg.files_dir.mkdir(parents=True, exist_ok=True)
    cfg.chroma_dir.mkdir(parents=True, exist_ok=True)
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    vs = VectorStore(str(cfg.chroma_dir))
    meta = MetadataManager(str(cfg.sqlite_path), vector_store=vs)

    doc_id = meta.create_document(
        file_name="test.txt",
        stored_path=str(cfg.files_dir / "test.txt"),
        file_ext=".txt",
        file_size=100,
    )
    meta.add_chunks(doc_id, [(0, "machine learning is great", f"{doc_id}_0")])
    meta.update_status(doc_id, "indexed", chunk_count=1)

    bm25 = BM25Retriever(meta)
    bm25.build_index()
    results = bm25.search("machine learning", top_k=5)
    assert len(results) >= 1
    assert results[0].document_id == doc_id