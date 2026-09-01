from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.config import Config
from core.metadata_manager import MetadataManager
from core.model_manager import ModelManager, ModelMismatchError, SwitchResult
from core.retriever import Retriever
from core.vector_store import ModelVersionInfo, VectorStore
from tests.conftest import FakeEmbedder


def _make_config(tmp_path: Path) -> Config:
    return Config(
        files_dir=tmp_path / "files",
        chroma_dir=tmp_path / "chroma_db",
        sqlite_path=tmp_path / "kb.sqlite",
        logs_dir=tmp_path / "logs",
        embedding_model="model-A",
        similarity_threshold=0.0,
    )


def test_check_consistency_unknown_version(tmp_path: Path):
    cfg = _make_config(tmp_path)
    cfg.files_dir.mkdir(parents=True, exist_ok=True)
    cfg.chroma_dir.mkdir(parents=True, exist_ok=True)
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    vs = VectorStore(str(cfg.chroma_dir))
    meta = MetadataManager(str(cfg.sqlite_path), vector_store=vs)
    mgr = ModelManager(cfg, vs, meta)

    consistent, msg = mgr.check_consistency()
    assert consistent is True
    assert "未知版本" in msg


def test_check_consistency_mismatch(tmp_path: Path):
    cfg = _make_config(tmp_path)
    cfg.files_dir.mkdir(parents=True, exist_ok=True)
    cfg.chroma_dir.mkdir(parents=True, exist_ok=True)
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    vs = VectorStore(str(cfg.chroma_dir), model_info=ModelVersionInfo(model="model-B", dimension=8))
    meta = MetadataManager(str(cfg.sqlite_path), vector_store=vs)
    mgr = ModelManager(cfg, vs, meta)

    consistent, msg = mgr.check_consistency()
    assert consistent is False
    assert "model-A" in msg or "model-B" in msg


def test_retriever_raises_on_mismatch(tmp_path: Path):
    cfg = _make_config(tmp_path)
    cfg.files_dir.mkdir(parents=True, exist_ok=True)
    cfg.chroma_dir.mkdir(parents=True, exist_ok=True)
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    vs = VectorStore(str(cfg.chroma_dir), model_info=ModelVersionInfo(model="model-B", dimension=8))
    meta = MetadataManager(str(cfg.sqlite_path), vector_store=vs)
    mgr = ModelManager(cfg, vs, meta)
    embedder = FakeEmbedder()
    retriever = Retriever(embedder, vs, meta, cfg, model_manager=mgr)

    with pytest.raises(ModelMismatchError):
        retriever.search("test query")


def test_retriever_no_check_without_manager(tmp_path: Path):
    cfg = _make_config(tmp_path)
    cfg.files_dir.mkdir(parents=True, exist_ok=True)
    cfg.chroma_dir.mkdir(parents=True, exist_ok=True)
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    vs = VectorStore(str(cfg.chroma_dir))
    meta = MetadataManager(str(cfg.sqlite_path), vector_store=vs)
    embedder = FakeEmbedder()
    retriever = Retriever(embedder, vs, meta, cfg)

    results = retriever.search("test query")
    assert results == []


def test_switch_model_success(tmp_path: Path):
    cfg = _make_config(tmp_path)
    cfg.files_dir.mkdir(parents=True, exist_ok=True)
    cfg.chroma_dir.mkdir(parents=True, exist_ok=True)
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    vs = VectorStore(str(cfg.chroma_dir))
    meta = MetadataManager(str(cfg.sqlite_path), vector_store=vs)
    mgr = ModelManager(cfg, vs, meta)

    rebuild_fn = MagicMock()
    result = mgr.switch_model("model-C", rebuild_fn)

    assert result.success is True
    assert result.backup_path is not None
    rebuild_fn.assert_called_once()
    assert cfg.embedding_model == "model-C"


def test_switch_model_rollback_on_failure(tmp_path: Path):
    cfg = _make_config(tmp_path)
    cfg.files_dir.mkdir(parents=True, exist_ok=True)
    cfg.chroma_dir.mkdir(parents=True, exist_ok=True)
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    vs = VectorStore(str(cfg.chroma_dir))
    meta = MetadataManager(str(cfg.sqlite_path), vector_store=vs)
    mgr = ModelManager(cfg, vs, meta)

    rebuild_fn = MagicMock(side_effect=RuntimeError("rebuild failed"))
    result = mgr.switch_model("model-C", rebuild_fn)

    assert result.success is False
    assert result.rolled_back is True
    assert "rebuild failed" in result.error
    assert cfg.embedding_model == "model-A"


def test_get_indexed_version_from_collection(tmp_path: Path):
    cfg = _make_config(tmp_path)
    cfg.files_dir.mkdir(parents=True, exist_ok=True)
    cfg.chroma_dir.mkdir(parents=True, exist_ok=True)
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    vs = VectorStore(str(cfg.chroma_dir), model_info=ModelVersionInfo(model="model-X", dimension=8))
    meta = MetadataManager(str(cfg.sqlite_path), vector_store=vs)
    mgr = ModelManager(cfg, vs, meta)

    indexed = mgr.get_indexed_version()
    assert indexed is not None
    assert indexed.model == "model-X"