"""嵌入后端抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseEmbeddingBackend(ABC):
    """嵌入后端抽象基类。

    子类须实现 backend_type/model_name/dimension 属性与
    is_available/is_model_available/embed_texts 方法。
    """

    @property
    @abstractmethod
    def backend_type(self) -> str:
        """后端类型标识。"""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """模型名称标识。"""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """嵌入向量维度。"""

    @abstractmethod
    def is_available(self) -> bool:
        """后端服务/依赖是否可用。"""

    @abstractmethod
    def is_model_available(self) -> bool:
        """模型是否已加载/就绪。"""

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量生成嵌入向量。"""

    def embed_query(self, query: str) -> list[float]:
        """生成单条查询的嵌入向量。"""
        return self.embed_texts([query])[0]