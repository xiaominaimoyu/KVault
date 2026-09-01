from __future__ import annotations

import pytest

from core.config import Config, LlamaCppConfig
from core.embedding_backends.factory import BackendFactory
from core.embedding_backends.llama_cpp_backend import LlamaCppBackend
from core.embedding_backends.ollama_backend import OllamaBackend


def test_factory_create_ollama():
    cfg = Config(embedding_backend="ollama", embedding_model="test-model")
    backend = BackendFactory.create(cfg)
    assert isinstance(backend, OllamaBackend)
    assert backend.backend_type == "ollama"


def test_factory_create_llama_cpp():
    cfg = Config(
        embedding_backend="llama_cpp",
        llama_cpp=LlamaCppConfig(model_path="/models/test.gguf"),
    )
    backend = BackendFactory.create(cfg)
    assert isinstance(backend, LlamaCppBackend)
    assert backend.backend_type == "llama_cpp"
    assert backend.model_path == "/models/test.gguf"


def test_factory_create_invalid():
    cfg = Config(embedding_backend="invalid")
    with pytest.raises(ValueError, match="未知的嵌入后端类型"):
        BackendFactory.create(cfg)