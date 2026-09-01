import logging

from core.config import Config
from core.embedding_backends.factory import BackendFactory
from core.embedding_backends.ollama_backend import OllamaBackend

logger = logging.getLogger(__name__)


class EmbeddingService:
    """嵌入服务门面，委托后端实例执行嵌入操作。

    既有调用方不传 config 时回退 OllamaBackend，行为等价现状。
    传入 config 时按 config.embedding_backend 分发创建对应后端。
    """

    def __init__(
        self,
        model: str = "modelscope.cn/Embedding-GGUF/bge-large-zh-v1.5:latest",
        base_url: str = "http://localhost:11434",
        batch_size: int = 32,
        dimension: int | None = None,
        config: Config | None = None,
    ):
        if config is not None:
            self._backend = BackendFactory.create(config)
        else:
            self._backend = OllamaBackend(
                model=model, base_url=base_url, batch_size=batch_size, dimension=dimension
            )

    @property
    def backend_type(self) -> str:
        return self._backend.backend_type

    @property
    def model_name(self) -> str:
        return self._backend.model_name

    @property
    def model(self) -> str:
        return self._backend.model_name

    @property
    def batch_size(self) -> int:
        return self._backend.batch_size

    @property
    def _dimension(self) -> int | None:
        return self._backend._dimension

    @property
    def dimension(self) -> int:
        return self._backend.dimension

    def is_available(self) -> bool:
        return self._backend.is_available()

    def is_model_available(self) -> bool:
        return self._backend.is_model_available()

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return self._backend.embed_texts(texts)

    def embed_query(self, query: str) -> list[float]:
        return self._backend.embed_query(query)
