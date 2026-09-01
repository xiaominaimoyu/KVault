from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.embedding_backends.ollama_backend import OllamaBackend


def _mock_ollama_client(embeddings=None):
    if embeddings is None:
        embeddings = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    client = MagicMock()
    client.list.return_value = {"models": [{"model": "test-model"}]}
    client.embed.return_value = {"embeddings": embeddings}
    return client


def test_ollama_backend_type():
    with patch("core.embedding_backends.ollama_backend.ollama") as mock_ollama:
        mock_ollama.Client.return_value = _mock_ollama_client()
        backend = OllamaBackend(model="test-model", base_url="http://localhost:11434")
        assert backend.backend_type == "ollama"
        assert backend.model_name == "test-model"


def test_ollama_embed_texts():
    with patch("core.embedding_backends.ollama_backend.ollama") as mock_ollama:
        mock_ollama.Client.return_value = _mock_ollama_client()
        backend = OllamaBackend(model="test-model")
        result = backend.embed_texts(["hello", "world"])
        assert len(result) == 2
        assert len(result[0]) == 3


def test_ollama_embed_texts_empty():
    with patch("core.embedding_backends.ollama_backend.ollama") as mock_ollama:
        mock_ollama.Client.return_value = _mock_ollama_client()
        backend = OllamaBackend(model="test-model")
        assert backend.embed_texts([]) == []


def test_ollama_is_available():
    with patch("core.embedding_backends.ollama_backend.ollama") as mock_ollama:
        mock_ollama.Client.return_value = _mock_ollama_client()
        backend = OllamaBackend(model="test-model")
        assert backend.is_available() is True


def test_ollama_is_available_false():
    with patch("core.embedding_backends.ollama_backend.ollama") as mock_ollama:
        client = MagicMock()
        client.list.side_effect = Exception("connection refused")
        mock_ollama.Client.return_value = client
        backend = OllamaBackend(model="test-model")
        assert backend.is_available() is False


def test_ollama_is_model_available():
    with patch("core.embedding_backends.ollama_backend.ollama") as mock_ollama:
        mock_ollama.Client.return_value = _mock_ollama_client()
        backend = OllamaBackend(model="test-model")
        assert backend.is_model_available() is True


def test_ollama_dimension_auto_detect():
    with patch("core.embedding_backends.ollama_backend.ollama") as mock_ollama:
        mock_ollama.Client.return_value = _mock_ollama_client(embeddings=[[0.1, 0.2, 0.3, 0.4]])
        backend = OllamaBackend(model="test-model")
        assert backend.dimension == 4