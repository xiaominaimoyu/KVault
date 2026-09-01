"""后端工厂，按配置分发创建后端实例。"""

from __future__ import annotations

from core.config import Config
from core.embedding_backends.base import BaseEmbeddingBackend
from core.embedding_backends.llama_cpp_backend import LlamaCppBackend
from core.embedding_backends.ollama_backend import OllamaBackend


class BackendFactory:
    """根据 config.embedding_backend 创建对应后端实例。"""

    @staticmethod
    def create(config: Config) -> BaseEmbeddingBackend:
        backend = config.embedding_backend
        if backend == "ollama":
            return OllamaBackend(
                model=config.embedding_model,
                base_url=config.ollama_base_url,
                batch_size=config.embedding_batch_size,
            )
        elif backend == "llama_cpp":
            return LlamaCppBackend(
                model_path=config.llama_cpp.model_path,
                n_gpu_layers=config.llama_cpp.n_gpu_layers,
                n_ctx=config.llama_cpp.n_ctx,
                embedding_dim=config.llama_cpp.embedding_dim,
                batch_size=config.embedding_batch_size,
            )
        else:
            raise ValueError(f"未知的嵌入后端类型: {backend}")