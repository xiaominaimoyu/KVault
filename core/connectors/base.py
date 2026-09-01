"""Connector 抽象基类与数据结构。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ConnectorDoc:
    """connector 拉取的文档数据。"""

    source_id: str
    name: str
    content: bytes
    metadata: dict = field(default_factory=dict)

    @property
    def ext(self) -> str:
        return Path(self.name).suffix.lower()


class BaseConnector(ABC):
    """connector 抽象基类。

    子类须实现 list / fetch / parse 三个方法。
    所有方法应在本地沙盒内执行，不执行远端脚本。
    """

    @abstractmethod
    def list(self) -> list[str]:
        """列出远端可同步的文档标识符列表。"""

    @abstractmethod
    def fetch(self, source_id: str) -> ConnectorDoc:
        """拉取指定文档的原始字节流。"""

    @abstractmethod
    def parse(self, doc: ConnectorDoc) -> str:
        """将原始字节流解析为文本。在本地沙盒内执行，不执行远端代码。"""

    def fetch_and_parse(self, source_id: str) -> tuple[ConnectorDoc, str]:
        """便捷方法：拉取并解析。"""
        doc = self.fetch(source_id)
        text = self.parse(doc)
        return doc, text