"""文档指纹计算模块。

基于文件路径 + mtime + size + 内容哈希（SHA-256）识别文档变更。
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DocFingerprint:
    """文档指纹，用于增量更新时的变更检测。"""

    stored_path: str
    mtime: float
    size: int
    content_hash: str


class FingerprintError(Exception):
    """指纹计算失败（如权限不足）。"""


class Fingerprint:
    """文档指纹计算器。"""

    @staticmethod
    def compute(file_path: str | Path) -> DocFingerprint:
        """计算文件指纹。

        Raises:
            FingerprintError: 文件不存在或无法读取。
        """
        p = Path(file_path)
        if not p.exists():
            raise FingerprintError(f"文件不存在: {p}")
        try:
            stat = p.stat()
            sha = hashlib.sha256()
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha.update(chunk)
            return DocFingerprint(
                stored_path=str(p),
                mtime=stat.st_mtime,
                size=stat.st_size,
                content_hash=sha.hexdigest(),
            )
        except PermissionError as e:
            raise FingerprintError(f"无法读取文件 {p}: {e}") from e
        except OSError as e:
            raise FingerprintError(f"读取文件失败 {p}: {e}") from e