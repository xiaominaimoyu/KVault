from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config import Config, LlamaCppConfig
from core.startup_check import StartupChecker


@pytest.fixture
def ollama_config(tmp_path: Path) -> Config:
    return Config(
        files_dir=tmp_path / "files",
        chroma_dir=tmp_path / "chroma_db",
        sqlite_path=tmp_path / "kb.sqlite",
        logs_dir=tmp_path / "logs",
        embedding_backend="ollama",
    )


@pytest.fixture
def llama_cpp_config(tmp_path: Path) -> Config:
    return Config(
        files_dir=tmp_path / "files",
        chroma_dir=tmp_path / "chroma_db",
        sqlite_path=tmp_path / "kb.sqlite",
        logs_dir=tmp_path / "logs",
        embedding_backend="llama_cpp",
        llama_cpp=LlamaCppConfig(model_path=str(tmp_path / "model.gguf")),
    )


def test_check_all_ollama_backend(ollama_config: Config):
    checker = StartupChecker(ollama_config)
    with patch("core.startup_check.ollama") as mock_ollama:
        client = MagicMock()
        client.list.return_value = {"models": [{"model": "bge-large-zh-v1.5"}]}
        mock_ollama.Client.return_value = client
        results = checker.check_all()
    names = [r.name for r in results]
    assert "Ollama 服务" in names
    assert "嵌入模型" in names
    assert "llama.cpp 依赖" not in names


def test_check_all_llama_cpp_backend(llama_cpp_config: Config):
    checker = StartupChecker(llama_cpp_config)
    with patch.dict("sys.modules", {"llama_cpp": MagicMock(Llama=MagicMock())}):
        results = checker.check_all()
    names = [r.name for r in results]
    assert "llama.cpp 依赖" in names
    assert "GGUF 模型" in names
    assert "Ollama 服务" not in names


def test_check_llama_cpp_dependency_missing(llama_cpp_config: Config):
    checker = StartupChecker(llama_cpp_config)
    original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

    def mock_import(name, *args, **kwargs):
        if name == "llama_cpp":
            raise ImportError("No module named 'llama_cpp'")
        return original_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        result = checker._check_llama_cpp_dependency()
    assert result.passed is False
    assert "pip install llama-cpp-python" in result.suggestion


def test_check_llama_cpp_dependency_present(llama_cpp_config: Config):
    checker = StartupChecker(llama_cpp_config)
    fake_module = MagicMock()
    fake_module.Llama = MagicMock()
    with patch.dict("sys.modules", {"llama_cpp": fake_module}):
        result = checker._check_llama_cpp_dependency()
    assert result.passed is True


def test_check_gguf_model_empty_path(tmp_path: Path):
    cfg = Config(
        files_dir=tmp_path / "files",
        chroma_dir=tmp_path / "chroma_db",
        sqlite_path=tmp_path / "kb.sqlite",
        logs_dir=tmp_path / "logs",
        embedding_backend="llama_cpp",
        llama_cpp=LlamaCppConfig(model_path=""),
    )
    checker = StartupChecker(cfg)
    result = checker._check_gguf_model()
    assert result.passed is False
    assert "未配置" in result.message


def test_check_gguf_model_nonexistent(llama_cpp_config: Config):
    checker = StartupChecker(llama_cpp_config)
    result = checker._check_gguf_model()
    assert result.passed is False
    assert "不存在" in result.message


def test_check_gguf_model_non_gguf(tmp_path: Path):
    model_file = tmp_path / "model.txt"
    model_file.write_bytes(b"not gguf")
    cfg = Config(
        files_dir=tmp_path / "files",
        chroma_dir=tmp_path / "chroma_db",
        sqlite_path=tmp_path / "kb.sqlite",
        logs_dir=tmp_path / "logs",
        embedding_backend="llama_cpp",
        llama_cpp=LlamaCppConfig(model_path=str(model_file)),
    )
    checker = StartupChecker(cfg)
    result = checker._check_gguf_model()
    assert result.passed is False
    assert ".gguf" in result.message


def test_check_gguf_model_valid(tmp_path: Path):
    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"fake gguf content")
    cfg = Config(
        files_dir=tmp_path / "files",
        chroma_dir=tmp_path / "chroma_db",
        sqlite_path=tmp_path / "kb.sqlite",
        logs_dir=tmp_path / "logs",
        embedding_backend="llama_cpp",
        llama_cpp=LlamaCppConfig(model_path=str(model_file)),
    )
    checker = StartupChecker(cfg)
    result = checker._check_gguf_model()
    assert result.passed is True
    assert "就绪" in result.message


def test_ollama_backend_unaffected_by_llama_cpp_missing(ollama_config: Config):
    checker = StartupChecker(ollama_config)
    original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

    def mock_import(name, *args, **kwargs):
        if name == "llama_cpp":
            raise ImportError("No module named 'llama_cpp'")
        return original_import(name, *args, **kwargs)

    with patch("core.startup_check.ollama") as mock_ollama:
        client = MagicMock()
        client.list.return_value = {"models": [{"model": "bge-large-zh-v1.5"}]}
        mock_ollama.Client.return_value = client
        with patch("builtins.__import__", side_effect=mock_import):
            results = checker.check_all()
    ollama_results = [r for r in results if "Ollama" in r.name or "嵌入" in r.name]
    assert len(ollama_results) == 2