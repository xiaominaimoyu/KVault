"""Connector 注册表。"""

from __future__ import annotations

from core.connectors.base import BaseConnector
from core.connectors.local_dir import LocalDirConnector
from core.connectors.github import GithubConnector
from core.connectors.notion import NotionConnector
from core.connectors.feishu import FeishuConnector


class ConnectorRegistry:
    """connector 类型注册表。"""

    _types: dict[str, type[BaseConnector]] = {
        "local_dir": LocalDirConnector,
        "github": GithubConnector,
        "notion": NotionConnector,
        "feishu": FeishuConnector,
    }

    @classmethod
    def register(cls, type_name: str, connector_cls: type[BaseConnector]) -> None:
        cls._types[type_name] = connector_cls

    @classmethod
    def get(cls, type_name: str) -> type[BaseConnector] | None:
        return cls._types.get(type_name)

    @classmethod
    def list_available(cls) -> list[str]:
        return sorted(cls._types.keys())

    @classmethod
    def create(cls, type_name: str, **kwargs) -> BaseConnector:
        connector_cls = cls._types.get(type_name)
        if connector_cls is None:
            raise ValueError(f"未知的 connector 类型: {type_name}，可用: {cls.list_available()}")
        return connector_cls(**kwargs)