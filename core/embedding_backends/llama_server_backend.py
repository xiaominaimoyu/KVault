"""llama.cpp server 嵌入后端（OpenAI 兼容 /v1/embeddings）。

与 ``llama_cpp`` 后端的区别：本后端**不**在进程内加载 GGUF 模型，
而是调用已启动的 ``llama-server`` HTTP 服务。适用于机器上已有
llama.cpp 推理服务的场景，无需安装 llama-cpp-python，也不重复占用显存。

服务启动示例::

    llama-server -m bge-m3-Q8_0.gguf --embedding --host 127.0.0.1 --port 8001
"""

from __future__ import annotations

import logging

import requests

from core.embedding_backends.base import BaseEmbeddingBackend

logger = logging.getLogger(__name__)


class LlamaServerBackend(BaseEmbeddingBackend):
    """llama.cpp server 嵌入后端。"""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8001",
        model: str = "",
        batch_size: int = 32,
        timeout: int = 120,
        dimension: int | None = None,
    ):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.model = (model or "").strip()
        self.batch_size = max(1, int(batch_size or 32))
        self.timeout = max(1, int(timeout or 120))
        self._dimension = dimension

    @property
    def backend_type(self) -> str:
        return "llama_cpp_server"

    @property
    def model_name(self) -> str:
        return self.model or "llama.cpp"

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            embedding = self.embed_query("probe")
            self._dimension = len(embedding)
        return self._dimension

    # ------------------------------------------------------------------ 可用性

    def _get(self, path: str):
        return requests.get(f"{self.base_url}{path}", timeout=min(self.timeout, 10))

    def is_available(self) -> bool:
        try:
            return self._get("/health").status_code == 200
        except Exception as e:
            logger.warning("llama.cpp 服务不可访问 (%s): %s", self.base_url, e)
            return False

    def list_models(self) -> list[str]:
        """读取服务已加载的模型 id 列表，失败时返回空列表。"""
        try:
            resp = self._get("/v1/models")
            resp.raise_for_status()
            data = resp.json().get("data", [])
            return [m.get("id") for m in data if m.get("id")]
        except Exception as e:
            logger.warning("获取 llama.cpp 模型列表失败: %s", e)
            return []

    def is_model_available(self) -> bool:
        models = self.list_models()
        if not models:
            return False
        if self.model:
            return self.model in models
        return True

    # ------------------------------------------------------------------ 嵌入

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        results: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            payload: dict = {"input": batch}
            if self.model:
                # llama-server 只加载一个模型时可以省略 model 字段
                payload["model"] = self.model

            try:
                resp = requests.post(
                    f"{self.base_url}/v1/embeddings",
                    json=payload,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                data = resp.json().get("data", [])
            except Exception as e:
                raise RuntimeError(
                    f"Embedding 失败（llama.cpp 服务 {self.base_url}）: {e}"
                ) from e

            # OpenAI 兼容接口不保证返回顺序，按 index 排序后再对齐输入
            data = sorted(data, key=lambda item: item.get("index", 0))
            embeddings = [item.get("embedding") for item in data]
            if len(embeddings) != len(batch) or any(e is None for e in embeddings):
                raise RuntimeError(
                    "llama.cpp 服务返回的向量数量不匹配: "
                    f"预期 {len(batch)}，实际 {len(embeddings)}"
                )

            for embedding in embeddings:
                if self._dimension is None:
                    self._dimension = len(embedding)
                elif len(embedding) != self._dimension:
                    raise RuntimeError(
                        f"嵌入维度不匹配: 预期 {self._dimension}, 实际 {len(embedding)}"
                    )
                results.append(embedding)
        return results
