from __future__ import annotations

import pytest

from core.config import Config, LlamaServerConfig
from core.embedding_backends.factory import BackendFactory
from core.embedding_backends.llama_server_backend import LlamaServerBackend


class _FakeResponse:
    def __init__(self, payload: dict | None = None, status_code: int = 200):
        self._payload = payload or {}
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_backend_identity_and_url_normalization():
    backend = LlamaServerBackend(base_url="http://127.0.0.1:8001/", model=" bge-m3 ")
    assert backend.backend_type == "llama_cpp_server"
    assert backend.model_name == "bge-m3"
    assert backend.base_url == "http://127.0.0.1:8001"


def test_is_available_and_model_available(monkeypatch):
    backend = LlamaServerBackend(model="bge-m3")

    def fake_get(url, timeout):
        if url.endswith("/health"):
            return _FakeResponse({})
        return _FakeResponse({"data": [{"id": "bge-m3"}]})

    monkeypatch.setattr(
        "core.embedding_backends.llama_server_backend.requests.get", fake_get
    )
    assert backend.is_available()
    assert backend.is_model_available()


def test_embed_texts_sorts_by_index_and_sets_dimension(monkeypatch):
    backend = LlamaServerBackend(model="bge-m3", batch_size=2)
    batches: list[list[str]] = []

    def fake_post(url, json, timeout):
        batches.append(json["input"])
        return _FakeResponse(
            {
                "data": [
                    {"index": 1, "embedding": [0.3, 0.4]},
                    {"index": 0, "embedding": [0.1, 0.2]},
                ]
            }
        )

    monkeypatch.setattr(
        "core.embedding_backends.llama_server_backend.requests.post", fake_post
    )

    result = backend.embed_texts(["a", "b"])
    assert batches == [["a", "b"]]
    assert result == [[0.1, 0.2], [0.3, 0.4]]
    assert backend.dimension == 2


def test_embed_texts_rejects_count_mismatch(monkeypatch):
    backend = LlamaServerBackend(model="bge-m3")

    def fake_post(url, json, timeout):
        return _FakeResponse({"data": [{"index": 0, "embedding": [0.1]}]})

    monkeypatch.setattr(
        "core.embedding_backends.llama_server_backend.requests.post", fake_post
    )

    with pytest.raises(RuntimeError, match="向量数量不匹配"):
        backend.embed_texts(["a", "b"])


def test_factory_creates_server_backend():
    cfg = Config(
        embedding_backend="llama_cpp_server",
        llama_server=LlamaServerConfig(
            base_url="http://127.0.0.1:8001", model="bge-m3", timeout=60
        ),
    )
    backend = BackendFactory.create(cfg)
    assert isinstance(backend, LlamaServerBackend)
    assert backend.timeout == 60
    assert backend.model_name == "bge-m3"


def test_invalid_server_base_url_rejected():
    cfg = Config(
        embedding_backend="llama_cpp_server",
        llama_server=LlamaServerConfig(base_url="127.0.0.1:8001"),
    )
    errors = cfg.validate()
    assert any("llama_server.base_url" in e for e in errors)


def test_server_section_ignored_for_ollama_backend():
    cfg = Config(
        embedding_backend="ollama",
        llama_server=LlamaServerConfig(base_url=""),
    )
    errors = cfg.validate()
    assert [e for e in errors if "llama_server" in e] == []
