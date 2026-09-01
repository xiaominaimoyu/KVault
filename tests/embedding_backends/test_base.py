from __future__ import annotations

import pytest

from core.embedding_backends.base import BaseEmbeddingBackend


def test_embed_query_delegates_to_embed_texts():
    class StubBackend(BaseEmbeddingBackend):
        @property
        def backend_type(self) -> str:
            return "stub"

        @property
        def model_name(self) -> str:
            return "stub-model"

        @property
        def dimension(self) -> int:
            return 4

        def is_available(self) -> bool:
            return True

        def is_model_available(self) -> bool:
            return True

        def embed_texts(self, texts: list[str]) -> list[list[float]]:
            return [[float(len(t))] * 4 for t in texts]

    backend = StubBackend()
    result = backend.embed_query("hello")
    assert result == [5.0, 5.0, 5.0, 5.0]


def test_abstract_methods_required():
    with pytest.raises(TypeError):
        BaseEmbeddingBackend()