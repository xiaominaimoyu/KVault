"""GitHub 仓库 connector，可选联网。

依赖 requests 或 gitpython，缺失时降级提示。
"""

from __future__ import annotations

import importlib.util
import logging

from core.connectors.base import BaseConnector, ConnectorDoc

logger = logging.getLogger(__name__)


def _has_requests() -> bool:
    return importlib.util.find_spec("requests") is not None


class GithubConnector(BaseConnector):
    """从 GitHub 仓库拉取文档。

    Args:
        repo: 仓库全名（如 "owner/repo"）
        branch: 分支名，默认 "main"
        token: GitHub token（可选，用于私有仓库或提高速率限制）
        path_filter: 仅拉取指定路径下的文件
    """

    def __init__(
        self,
        repo: str,
        branch: str = "main",
        token: str | None = None,
        path_filter: str = "",
    ):
        self._repo = repo
        self._branch = branch
        self._token = token
        self._path_filter = path_filter
        self._available = _has_requests()

    def list(self) -> list[str]:
        if not self._available:
            logger.warning("requests 未安装，GitHub connector 不可用")
            return []
        import requests

        headers = {"Accept": "application/vnd.github.v3+json"}
        if self._token:
            headers["Authorization"] = f"token {self._token}"
        url = f"https://api.github.com/repos/{self._repo}/git/trees/{self._branch}?recursive=1"
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        tree = resp.json().get("tree", [])
        result = []
        for item in tree:
            if item["type"] != "blob":
                continue
            path = item["path"]
            if self._path_filter and not path.startswith(self._path_filter):
                continue
            result.append(path)
        return result

    def fetch(self, source_id: str) -> ConnectorDoc:
        if not self._available:
            raise RuntimeError("requests 未安装，GitHub connector 不可用")
        import requests

        headers = {"Accept": "application/vnd.github.v3.raw"}
        if self._token:
            headers["Authorization"] = f"token {self._token}"
        url = f"https://api.github.com/repos/{self._repo}/contents/{source_id}?ref={self._branch}"
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        content = resp.content
        return ConnectorDoc(
            source_id=source_id,
            name=source_id.rsplit("/", 1)[-1],
            content=content,
            metadata={"repo": self._repo, "branch": self._branch, "path": source_id},
        )

    def parse(self, doc: ConnectorDoc) -> str:
        return doc.content.decode("utf-8", errors="ignore")