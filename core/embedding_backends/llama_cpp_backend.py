"""llama.cpp 嵌入后端，懒加载 + 延迟 import。"""

from __future__ import annotations

import logging
from pathlib import Path

from core.embedding_backends.base import BaseEmbeddingBackend
from core.embedding_backends.exceptions import BackendUnavailableError, ModelLoadError

logger = logging.getLogger(__name__)


class LlamaCppBackend(BaseEmbeddingBackend):
    """llama.cpp 嵌入后端。

    通过 llama-cpp-python 在进程内加载 GGUF 模型生成嵌入向量。
    模型懒加载：构造时不加载，首次 embed_texts 时加载。
    """

    def __init__(
        self,
        model_path: str = "",
        n_gpu_layers: int = 0,
        n_ctx: int = 2048,
        embedding_dim: int | None = None,
        batch_size: int = 32,
    ):
        self.model_path = model_path
        self.n_gpu_layers = n_gpu_layers
        self.n_ctx = n_ctx
        self.batch_size = batch_size
        self._dimension = embedding_dim
        self._model = None
        self._model_loaded = False

    @property
    def backend_type(self) -> str:
        return "llama_cpp"

    @property
    def model_name(self) -> str:
        return Path(self.model_path).name if self.model_path else ""

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            embedding = self.embed_query("probe")
            self._dimension = len(embedding)
        return self._dimension

    def is_available(self) -> bool:
        try:
            import llama_cpp
            return hasattr(llama_cpp, "Llama")
        except ImportError:
            return False

    def is_model_available(self) -> bool:
        if not self.model_path:
            return False
        p = Path(self.model_path)
        return p.exists() and p.suffix.lower() == ".gguf"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        if not self._model_loaded:
            self._load_model()

        results: list[list[float]] = []
        for text in texts:
            try:
                embedding = self._model.embed(text)
                if self._dimension is None:
                    self._dimension = len(embedding)
                elif len(embedding) != self._dimension:
                    raise RuntimeError(
                        f"嵌入维度不匹配: 预期 {self._dimension}, 实际 {len(embedding)}"
                    )
                results.append(embedding)
            except RuntimeError:
                raise
            except Exception as e:
                raise RuntimeError(f"嵌入生成失败（llama.cpp）: {e}") from e
        return results

    def _load_model(self):
        p = Path(self.model_path) if self.model_path else None
        if p is None or not p.exists():
            raise ModelLoadError(f"模型文件不存在: {self.model_path}")
        if p.suffix.lower() != ".gguf":
            raise ModelLoadError(f"模型文件必须为 .gguf 格式: {self.model_path}")

        try:
            from llama_cpp import Llama
        except ImportError:
            raise BackendUnavailableError(
                "未安装 llama-cpp-python，请执行 pip install llama-cpp-python"
            )

        try:
            self._model = Llama(
                model_path=str(p),
                n_gpu_layers=self.n_gpu_layers,
                n_ctx=self.n_ctx,
                embedding=True,
            )
            self._model_loaded = True
            logger.info("llama.cpp 模型已加载: %s", self.model_path)
        except Exception as e:
            raise ModelLoadError(f"模型加载失败: {e}") from e