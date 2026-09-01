from __future__ import annotations

from pathlib import Path

from core.config import Config
from core.document_parser import DocumentParser
from core.incremental_updater import IncrementalUpdater
from core.metadata_manager import MetadataManager
from core.text_splitter import KnowledgeTextSplitter
from core.vector_store import VectorStore
from tests.conftest import FakeEmbedder


def _make_updater(tmp_path: Path):
    cfg = Config(
        files_dir=tmp_path / "files",
        chroma_dir=tmp_path / "chroma_db",
        sqlite_path=tmp_path / "kb.sqlite",
        logs_dir=tmp_path / "logs",
        chunk_size=200,
        chunk_overlap=20,
        similarity_threshold=0.0,
    )
    cfg.files_dir.mkdir(parents=True, exist_ok=True)
    cfg.chroma_dir.mkdir(parents=True, exist_ok=True)
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    vs = VectorStore(str(cfg.chroma_dir))
    meta = MetadataManager(str(cfg.sqlite_path), vector_store=vs)
    parser = DocumentParser()
    splitter = KnowledgeTextSplitter(chunk_size=cfg.chunk_size, chunk_overlap=cfg.chunk_overlap)
    embedder = FakeEmbedder()
    updater = IncrementalUpdater(cfg, parser, splitter, embedder, vs, meta)
    return updater, cfg, vs, meta


def test_scan_diffs_empty(tmp_path: Path):
    updater, *_ = _make_updater(tmp_path)
    report = updater.scan_diffs()
    assert report.added == []
    assert report.modified == []
    assert report.deleted == []


def test_scan_diffs_added(tmp_path: Path):
    updater, cfg, *_ = _make_updater(tmp_path)
    (cfg.files_dir / "new.txt").write_text("new content", encoding="utf-8")
    report = updater.scan_diffs()
    assert len(report.added) == 1
    assert report.modified == []
    assert report.deleted == []


def test_incremental_update_added(tmp_path: Path):
    updater, cfg, vs, meta = _make_updater(tmp_path)
    (cfg.files_dir / "a.txt").write_text("alpha beta gamma", encoding="utf-8")
    report = updater.scan_diffs()
    result = updater.update(report)
    assert result.success_count == 1
    assert result.fail_count == 0
    assert vs.count() == 1
    assert len(meta.list_documents()) == 1


def test_incremental_update_modified(tmp_path: Path):
    from core.ingest import ingest_document
    updater, cfg, vs, meta = _make_updater(tmp_path)
    f = cfg.files_dir / "a.txt"
    f.write_text("original content here", encoding="utf-8")
    ingest_document(str(f), cfg, updater.parser, updater.splitter, updater.embedder, vs, meta)
    before = vs.count()

    f.write_text("modified content here totally different", encoding="utf-8")
    report = updater.scan_diffs()
    assert len(report.modified) == 1
    result = updater.update(report)
    assert result.success_count == 1
    assert vs.count() == before


def test_incremental_update_deleted(tmp_path: Path):
    from core.ingest import ingest_document
    updater, cfg, vs, meta = _make_updater(tmp_path)
    f = cfg.files_dir / "a.txt"
    f.write_text("to be deleted", encoding="utf-8")
    ingest_document(str(f), cfg, updater.parser, updater.splitter, updater.embedder, vs, meta)
    assert vs.count() > 0

    f.unlink()
    report = updater.scan_diffs()
    assert len(report.deleted) == 1
    result = updater.update(report)
    assert vs.count() == 0
    assert len(meta.list_documents()) == 0


def test_rebuild_all(tmp_path: Path):
    from core.ingest import ingest_document
    updater, cfg, vs, meta = _make_updater(tmp_path)
    (cfg.files_dir / "a.txt").write_text("content A", encoding="utf-8")
    (cfg.files_dir / "b.txt").write_text("content B", encoding="utf-8")
    ingest_document(
        str(cfg.files_dir / "a.txt"), cfg, updater.parser, updater.splitter,
        updater.embedder, vs, meta,
    )
    result = updater.rebuild_all()
    assert result.success_count == 2
    assert len(meta.list_documents()) == 2


def test_dirty_data_does_not_block(tmp_path: Path):
    updater, cfg, vs, meta = _make_updater(tmp_path)
    (cfg.files_dir / "good.txt").write_text("good content", encoding="utf-8")
    (cfg.files_dir / "bad.bin").write_bytes(b"\x00\x01\x02\x03")
    report = updater.scan_diffs()
    result = updater.update(report)
    assert result.success_count + result.fail_count == 2
    assert len(meta.list_documents()) >= 1