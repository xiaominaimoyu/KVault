from __future__ import annotations

from pathlib import Path

from core.config import Config, HybridSearchConfig
from core.metadata_manager import MetadataManager
from core.retriever import Retriever
from core.vector_store import VectorStore
from tests.conftest import FakeEmbedder


def _setup(tmp_path: Path, hybrid_enabled: bool = False):
    cfg = Config(
        files_dir=tmp_path / "files",
        chroma_dir=tmp_path / "chroma_db",
        sqlite_path=tmp_path / "kb.sqlite",
        logs_dir=tmp_path / "logs",
        similarity_threshold=0.0,
        hybrid_search=HybridSearchConfig(enabled=hybrid_enabled),
    )
    cfg.files_dir.mkdir(parents=True, exist_ok=True)
    cfg.chroma_dir.mkdir(parents=True, exist_ok=True)
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    vs = VectorStore(str(cfg.chroma_dir))
    meta = MetadataManager(str(cfg.sqlite_path), vector_store=vs)
    embedder = FakeEmbedder()
    retriever = Retriever(embedder, vs, meta, cfg)
    return cfg, vs, meta, embedder, retriever


def test_hybrid_disabled_uses_vector(tmp_path: Path):
    cfg, vs, meta, embedder, retriever = _setup(tmp_path, hybrid_enabled=False)
    text = "alpha beta gamma"
    doc_id = meta.create_document(
        file_name="a.txt", stored_path=str(cfg.files_dir / "a.txt"),
        file_ext=".txt", file_size=len(text),
    )
    emb = embedder.embed_query(text)
    vs.add_chunks([f"{doc_id}_0"], [text], [emb], [{"document_id": doc_id, "file_name": "a.txt"}])
    meta.add_chunks(doc_id, [(0, text, f"{doc_id}_0")])
    meta.update_status(doc_id, "indexed", chunk_count=1)

    results = retriever.search(text)
    assert len(results) >= 1
    assert all(r.hit_source == "vector" for r in results)


def test_hybrid_enabled_returns_results(tmp_path: Path):
    cfg, vs, meta, embedder, retriever = _setup(tmp_path, hybrid_enabled=True)
    text = "alpha beta gamma"
    doc_id = meta.create_document(
        file_name="a.txt", stored_path=str(cfg.files_dir / "a.txt"),
        file_ext=".txt", file_size=len(text),
    )
    emb = embedder.embed_query(text)
    vs.add_chunks([f"{doc_id}_0"], [text], [emb], [{"document_id": doc_id, "file_name": "a.txt"}])
    meta.add_chunks(doc_id, [(0, text, f"{doc_id}_0")])
    meta.update_status(doc_id, "indexed", chunk_count=1)

    results = retriever.search(text)
    assert len(results) >= 1


def test_search_result_has_new_fields(tmp_path: Path):
    cfg, vs, meta, embedder, retriever = _setup(tmp_path)
    results = retriever.search("nonexistent")
    for r in results:
        assert hasattr(r, "partition")
        assert hasattr(r, "hit_source")
        assert r.partition == ""