import logging

import ollama

logger = logging.getLogger(__name__)


class EmbeddingService:
    """通过 Ollama 生成文本 Embedding。"""

    def __init__(
        self,
        model: str = "modelscope.cn/Embedding-GGUF/bge-large-zh-v1.5:latest",
        base_url: str = "http://localhost:11434",
        batch_size: int = 32,
        dimension: int | None = None,
    ):
        self.model = model
        self.batch_size = batch_size
        self._dimension = dimension
        self.client = ollama.Client(host=base_url)
        self._resolve_model_name()

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            # Auto-detect by embedding a short probe text
            embedding = self.embed_query("probe")
            self._dimension = len(embedding)
        return self._dimension

    def is_available(self) -> bool:
        try:
            self.client.list()
            return True
        except Exception as e:
            logger.warning("Ollama 服务不可访问: %s", e)
            return False

    def _resolve_model_name(self):
        try:
            models = self.client.list()
            names = {m.get("model", "") for m in models.get("models", [])}
            if self.model in names:
                return
            short_name = self.model.split("/")[-1]
            short_name = short_name.replace(":latest", "")
            for name in names:
                if short_name in name or name.endswith(f":{short_name}"):
                    old_name = self.model
                    self.model = name
                    logger.info("Resolved model name: %s -> %s", old_name, name)
                    return
        except Exception as e:
            logger.warning("解析模型名称失败: %s", e)

    def is_model_available(self) -> bool:
        try:
            models = self.client.list()
            names = {m.get("model", "") for m in models.get("models", [])}
            return self.model in names
        except Exception as e:
            logger.warning("检查 Ollama 模型失败: %s", e)
            return False

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        results: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            try:
                resp = self.client.embed(model=self.model, input=batch)
                embeddings = resp.get("embeddings", [])
                if not embeddings:
                    raise RuntimeError("Ollama 返回空 embeddings")
                if self._dimension is None and embeddings:
                    self._dimension = len(embeddings[0])
                results.extend(embeddings)
            except Exception as e:
                logger.error("Embedding 失败: %s", e)
                raise RuntimeError(f"Embedding 失败 ({self.model}): {e}") from e
        return results

    def embed_query(self, query: str) -> list[float]:
        return self.embed_texts([query])[0]
