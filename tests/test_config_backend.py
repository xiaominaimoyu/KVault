from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.config import Config, LlamaCppConfig


def test_default_backend_is_ollama():
    cfg = Config()
    assert cfg.embedding_backend == "ollama"


def test_default_llama_cpp_config():
    cfg = Config()
    assert cfg.llama_cpp == LlamaCppConfig()
    assert cfg.llama_cpp.model_path == ""
    assert cfg.llama_cpp.n_gpu_layers == 0
    assert cfg.llama_cpp.n_ctx == 2048
    assert cfg.llama_cpp.embedding_dim is None


def test_old_config_json_migration(tmp_path: Path):
    old_config = {
        "embedding_model": "bge-large-zh-v1.5",
        "ollama_base_url": "http://localhost:11434",
        "embedding_batch_size": 32,
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(old_config), encoding="utf-8")
    cfg = Config.load(str(config_file))
    assert cfg.embedding_backend == "ollama"
    assert cfg.llama_cpp == LlamaCppConfig()


def test_llama_cpp_backend_empty_model_path_invalid():
    cfg = Config(
        embedding_backend="llama_cpp",
        llama_cpp=LlamaCppConfig(model_path=""),
    )
    errors = cfg.validate()
    assert any("model_path" in e for e in errors)


def test_invalid_backend_type():
    cfg = Config(embedding_backend="invalid_backend")
    errors = cfg.validate()
    assert any("embedding_backend" in e for e in errors)


def test_ollama_backend_llama_cpp_section_optional():
    cfg = Config(embedding_backend="ollama")
    errors = cfg.validate()
    backend_errors = [e for e in errors if "llama_cpp" in e]
    assert backend_errors == []


def test_llama_cpp_subfield_defaults(tmp_path: Path):
    config_data = {
        "embedding_backend": "llama_cpp",
        "llama_cpp": {"model_path": "/path/to/model.gguf"},
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config_data), encoding="utf-8")
    cfg = Config.load(str(config_file))
    assert cfg.llama_cpp.model_path == "/path/to/model.gguf"
    assert cfg.llama_cpp.n_gpu_layers == 0
    assert cfg.llama_cpp.n_ctx == 2048
    assert cfg.llama_cpp.embedding_dim is None


def test_save_load_roundtrip(tmp_path: Path):
    cfg = Config(
        embedding_backend="llama_cpp",
        llama_cpp=LlamaCppConfig(
            model_path="/models/bge.gguf",
            n_gpu_layers=2,
            n_ctx=4096,
            embedding_dim=1024,
        ),
    )
    config_file = tmp_path / "config.json"
    cfg.save(str(config_file))
    loaded = Config.load(str(config_file))
    assert loaded.embedding_backend == "llama_cpp"
    assert loaded.llama_cpp.model_path == "/models/bge.gguf"
    assert loaded.llama_cpp.n_gpu_layers == 2
    assert loaded.llama_cpp.n_ctx == 4096
    assert loaded.llama_cpp.embedding_dim == 1024


def test_llama_cpp_validate_negative_gpu_layers():
    cfg = Config(
        embedding_backend="llama_cpp",
        llama_cpp=LlamaCppConfig(model_path="/m.gguf", n_gpu_layers=-1),
    )
    errors = cfg.validate()
    assert any("n_gpu_layers" in e for e in errors)


def test_llama_cpp_validate_small_ctx():
    cfg = Config(
        embedding_backend="llama_cpp",
        llama_cpp=LlamaCppConfig(model_path="/m.gguf", n_ctx=256),
    )
    errors = cfg.validate()
    assert any("n_ctx" in e for e in errors)


def test_llama_cpp_valid_config():
    cfg = Config(
        embedding_backend="llama_cpp",
        llama_cpp=LlamaCppConfig(model_path="/models/bge.gguf", n_ctx=2048),
    )
    errors = cfg.validate()
    backend_errors = [e for e in errors if "llama_cpp" in e or "embedding_backend" in e]
    assert backend_errors == []