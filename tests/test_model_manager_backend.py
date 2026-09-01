from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.config import Config, LlamaCppConfig
from core.metadata_manager import MetadataManager
from core.model_manager import ModelManager, SwitchResult
from core.vector_store import ModelVersionInfo, VectorStore


def _make_config(tmp_path: Path, backend: str = "ollama") -> Config:
    cfg = Config(
        files_dir=tmp_path / "files",
        chroma_dir=tmp_path / "chroma_db",
        sqlite_path=tmp_path / "kb.sqlite",
        logs_dir=tmp_path / "logs",
        embedding_model="model-A",
        similarity_threshold=0.0,
        embedding_backend=backend,
    )
    if backend == "llama_cpp":
        cfg.llama_cpp = LlamaCppConfig(model_path=str(tmp_path / "models" / "bge.gguf"))
    return cfg


def _setup(tmp_path: Path, backend: str = "ollama"):
    cfg = _make_config(tmp_path, backend)
    cfg.files_dir.mkdir(parents=True, exist_ok=True)
    cfg.chroma_dir.mkdir(parents=True, exist_ok=True)
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    vs = VectorStore(str(cfg.chroma_dir))
    meta = MetadataManager(str(cfg.sqlite_path), vector_store=vs)
    return cfg, vs, meta, ModelManager(cfg, vs, meta)


# --- 测试点 ①：get_config_version 按后端取模型标识 ---

def test_get_config_version_ollama(tmp_path: Path):
    cfg, vs, meta, mgr = _setup(tmp_path, "ollama")
    version = mgr.get_config_version()
    assert version.model == "model-A"


def test_get_config_version_llama_cpp(tmp_path: Path):
    cfg, vs, meta, mgr = _setup(tmp_path, "llama_cpp")
    version = mgr.get_config_version()
    assert version.model == "bge.gguf"


# --- 测试点 ②：switch_backend 成功 ---

def test_switch_backend_ollama_to_llama_cpp_success(tmp_path: Path):
    cfg, vs, meta, mgr = _setup(tmp_path, "ollama")
    new_gguf_path = str(tmp_path / "models" / "new-model.gguf")

    rebuild_fn = MagicMock()
    result = mgr.switch_backend("llama_cpp", new_gguf_path, rebuild_fn)

    assert result.success is True
    assert result.backup_path is not None
    rebuild_fn.assert_called_once()
    assert cfg.embedding_backend == "llama_cpp"
    assert cfg.llama_cpp.model_path == new_gguf_path


def test_switch_backend_llama_cpp_to_ollama_success(tmp_path: Path):
    cfg, vs, meta, mgr = _setup(tmp_path, "llama_cpp")

    rebuild_fn = MagicMock()
    result = mgr.switch_backend("ollama", "model-B", rebuild_fn)

    assert result.success is True
    assert cfg.embedding_backend == "ollama"
    assert cfg.embedding_model == "model-B"


# --- 测试点 ③：switch_backend 重建失败时回滚 ---

def test_switch_backend_rollback_on_rebuild_failure(tmp_path: Path):
    cfg, vs, meta, mgr = _setup(tmp_path, "ollama")
    original_model = cfg.embedding_model
    original_backend = cfg.embedding_backend

    rebuild_fn = MagicMock(side_effect=RuntimeError("rebuild failed"))
    result = mgr.switch_backend("llama_cpp", str(tmp_path / "x.gguf"), rebuild_fn)

    assert result.success is False
    assert result.rolled_back is True
    assert "rebuild failed" in result.error
    assert cfg.embedding_backend == original_backend
    assert cfg.embedding_model == original_model


def test_switch_backend_rollback_on_validation_failure(tmp_path: Path):
    cfg, vs, meta, mgr = _setup(tmp_path, "ollama")

    rebuild_fn = MagicMock()
    mgr.get_indexed_version = MagicMock(
        return_value=ModelVersionInfo(model="unexpected-model", dimension=8, created_at=1.0)
    )

    result = mgr.switch_backend("llama_cpp", str(tmp_path / "new.gguf"), rebuild_fn)

    assert result.success is False
    assert result.rolled_back is True
    assert cfg.embedding_backend == "ollama"


# --- 测试点 ④：check_consistency 检测后端切换后模型标识变化 ---

def test_check_consistency_detects_backend_switch(tmp_path: Path):
    cfg = _make_config(tmp_path, "ollama")
    cfg.files_dir.mkdir(parents=True, exist_ok=True)
    cfg.chroma_dir.mkdir(parents=True, exist_ok=True)
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    vs = VectorStore(
        str(cfg.chroma_dir),
        model_info=ModelVersionInfo(model="model-A", dimension=8, created_at=1.0),
    )
    meta = MetadataManager(str(cfg.sqlite_path), vector_store=vs)
    mgr = ModelManager(cfg, vs, meta)

    consistent, _ = mgr.check_consistency()
    assert consistent is True

    cfg.embedding_backend = "llama_cpp"
    cfg.llama_cpp = LlamaCppConfig(model_path=str(tmp_path / "different.gguf"))

    consistent, msg = mgr.check_consistency()
    assert consistent is False
    assert "model-A" in msg or "different.gguf" in msg


# --- 测试点 ⑤：维度变化且索引非空时阻止检索 ---

def test_dimension_change_blocks_retrieval(tmp_path: Path):
    from core.retriever import Retriever
    from tests.conftest import FakeEmbedder

    cfg = _make_config(tmp_path, "ollama")
    cfg.files_dir.mkdir(parents=True, exist_ok=True)
    cfg.chroma_dir.mkdir(parents=True, exist_ok=True)
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    vs = VectorStore(
        str(cfg.chroma_dir),
        model_info=ModelVersionInfo(model="model-A", dimension=1024, created_at=1.0),
    )
    meta = MetadataManager(str(cfg.sqlite_path), vector_store=vs)
    mgr = ModelManager(cfg, vs, meta)

    cfg.embedding_backend = "llama_cpp"
    cfg.llama_cpp = LlamaCppConfig(model_path=str(tmp_path / "switched.gguf"))

    embedder = FakeEmbedder()
    retriever = Retriever(embedder, vs, meta, cfg, model_manager=mgr)

    with pytest.raises(Exception):
        retriever.search("test query")