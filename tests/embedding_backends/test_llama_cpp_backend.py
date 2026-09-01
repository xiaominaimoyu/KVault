from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.embedding_backends.exceptions import BackendUnavailableError, ModelLoadError
from core.embedding_backends.llama_cpp_backend import LlamaCppBackend


def test_backend_type():
    backend = LlamaCppBackend(model_path="/models/test.gguf")
    assert backend.backend_type == "llama_cpp"
    assert backend.model_name == "test.gguf"


def test_lazy_loading_no_model_at_construction():
    backend = LlamaCppBackend(model_path="/models/test.gguf")
    assert backend._model is None
    assert backend._model_loaded is False


def test_embed_texts_empty_no_loading():
    backend = LlamaCppBackend(model_path="/models/test.gguf")
    assert backend.embed_texts([]) == []
    assert backend._model_loaded is False


def test_is_available_false_when_missing():
    backend = LlamaCppBackend(model_path="/models/test.gguf")
    with patch.dict("sys.modules", {"llama_cpp": None}):
        assert backend.is_available() is False


def test_is_available_true_when_present():
    backend = LlamaCppBackend(model_path="/models/test.gguf")
    fake_module = MagicMock()
    fake_module.Llama = MagicMock()
    with patch.dict("sys.modules", {"llama_cpp": fake_module}):
        assert backend.is_available() is True


def test_is_model_available_false_no_path():
    backend = LlamaCppBackend(model_path="")
    assert backend.is_model_available() is False


def test_is_model_available_false_nonexistent(tmp_path: Path):
    backend = LlamaCppBackend(model_path=str(tmp_path / "nonexistent.gguf"))
    assert backend.is_model_available() is False


def test_is_model_available_true(tmp_path: Path):
    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"fake gguf")
    backend = LlamaCppBackend(model_path=str(model_file))
    assert backend.is_model_available() is True


def test_load_model_nonexistent_file():
    backend = LlamaCppBackend(model_path="/nonexistent/model.gguf")
    with pytest.raises(ModelLoadError, match="模型文件不存在"):
        backend._load_model()


def test_load_model_non_gguf_extension(tmp_path: Path):
    model_file = tmp_path / "model.txt"
    model_file.write_bytes(b"not gguf")
    backend = LlamaCppBackend(model_path=str(model_file))
    with pytest.raises(ModelLoadError, match="必须为 .gguf"):
        backend._load_model()


def test_load_model_missing_dependency(tmp_path: Path):
    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"fake gguf")
    backend = LlamaCppBackend(model_path=str(model_file))

    original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

    def mock_import(name, *args, **kwargs):
        if name == "llama_cpp":
            raise ImportError("No module named 'llama_cpp'")
        return original_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        with pytest.raises(BackendUnavailableError, match="未安装 llama-cpp-python"):
            backend._load_model()


def test_embed_texts_with_mock_model(tmp_path: Path):
    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"fake gguf")
    backend = LlamaCppBackend(model_path=str(model_file), embedding_dim=4)

    fake_model = MagicMock()
    fake_model.embed.return_value = [0.1, 0.2, 0.3, 0.4]
    fake_llama = MagicMock()
    fake_llama.Llama = MagicMock(return_value=fake_model)

    with patch.dict("sys.modules", {"llama_cpp": fake_llama}):
        result = backend.embed_texts(["hello", "world"])
    assert len(result) == 2
    assert result[0] == [0.1, 0.2, 0.3, 0.4]
    assert backend._model_loaded is True


def test_embed_texts_dimension_mismatch(tmp_path: Path):
    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"fake gguf")
    backend = LlamaCppBackend(model_path=str(model_file), embedding_dim=4)

    fake_model = MagicMock()
    fake_model.embed.return_value = [0.1, 0.2, 0.3]
    fake_llama = MagicMock()
    fake_llama.Llama = MagicMock(return_value=fake_model)

    with patch.dict("sys.modules", {"llama_cpp": fake_llama}):
        with pytest.raises(RuntimeError, match="维度不匹配"):
            backend.embed_texts(["hello"])