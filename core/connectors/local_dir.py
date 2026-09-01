"""本地目录 connector，完全离线无联网请求。"""

from __future__ import annotations

from pathlib import Path

from core.connectors.base import BaseConnector, ConnectorDoc


class LocalDirConnector(BaseConnector):
    """监听本地目录，遍历文件并读取内容。

    Args:
        dir_path: 本地目录路径
        extensions: 允许的文件扩展名集合（如 {".txt", ".md"}），为空则全部允许
    """

    def __init__(self, dir_path: str, extensions: set[str] | None = None):
        self._dir = Path(dir_path)
        self._extensions = extensions or set()

    def list(self) -> list[str]:
        if not self._dir.exists():
            return []
        result = []
        for p in sorted(self._dir.rglob("*")):
            if not p.is_file():
                continue
            if self._extensions and p.suffix.lower() not in self._extensions:
                continue
            result.append(p.relative_to(self._dir).as_posix())
        return result

    def fetch(self, source_id: str) -> ConnectorDoc:
        path = self._dir / source_id
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {source_id}")
        content = path.read_bytes()
        return ConnectorDoc(
            source_id=source_id,
            name=Path(source_id).name,
            content=content,
            metadata={"source": str(path)},
        )

    def parse(self, doc: ConnectorDoc) -> str:
        return doc.content.decode("utf-8", errors="ignore")