"""飞书 connector 预留接口占位。"""

from __future__ import annotations

from core.connectors.base import BaseConnector, ConnectorDoc


class FeishuConnector(BaseConnector):
    """飞书 connector（未实现）。

    调用时返回明确「未实现」提示而非抛未捕获异常。
    """

    NOT_IMPLEMENTED_MSG = "飞书 connector 尚未实现，请使用 LocalDirConnector 或 GithubConnector"

    def __init__(self, app_id: str | None = None, app_secret: str | None = None):
        self._app_id = app_id
        self._app_secret = app_secret

    def list(self) -> list[str]:
        return []

    def fetch(self, source_id: str) -> ConnectorDoc:
        return ConnectorDoc(
            source_id=source_id,
            name=source_id,
            content=b"",
            metadata={"warning": self.NOT_IMPLEMENTED_MSG},
        )

    def parse(self, doc: ConnectorDoc) -> str:
        return self.NOT_IMPLEMENTED_MSG