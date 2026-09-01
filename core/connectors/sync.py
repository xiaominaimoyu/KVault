"""Connector 同步编排，复用增量更新入库。"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from core.connectors.base import BaseConnector

logger = logging.getLogger(__name__)


@dataclass
class SyncReport:
    """同步结果报告。"""

    connector_type: str
    total: int = 0
    synced: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    duration: float = 0.0


class ConnectorSync:
    """connector 同步器。

    调用 connector.list() → fetch() → parse()，
    通过回调函数入库（复用 IncrementalUpdater 或直接 ingest）。
    """

    def __init__(self, connector: BaseConnector, connector_type: str = ""):
        self._connector = connector
        self._type = connector_type or type(connector).__name__

    def sync(self, ingest_fn=None) -> SyncReport:
        """执行同步。

        Args:
            ingest_fn: 回调函数 (source_id: str, name: str, content: str, metadata: dict) -> bool
                       返回 True 表示新入库，False 表示跳过（已存在）。
                       若为 None 则仅拉取解析不入库。

        Returns:
            SyncReport 同步结果报告。
        """
        start = time.time()
        report = SyncReport(connector_type=self._type)

        try:
            source_ids = self._connector.list()
        except Exception as e:
            logger.error("connector list 失败: %s", e)
            report.errors.append(f"list failed: {e}")
            report.duration = time.time() - start
            return report

        report.total = len(source_ids)

        for source_id in source_ids:
            try:
                doc, text = self._connector.fetch_and_parse(source_id)
                if ingest_fn is not None:
                    result = ingest_fn(source_id, doc.name, text, doc.metadata)
                    if result:
                        report.synced += 1
                    else:
                        report.skipped += 1
                else:
                    report.synced += 1
            except Exception as e:
                logger.warning("同步 %s 失败: %s", source_id, e)
                report.failed += 1
                report.errors.append(f"{source_id}: {e}")

        report.duration = time.time() - start
        logger.info(
            "同步完成: total=%d synced=%d skipped=%d failed=%d (%.1fs)",
            report.total, report.synced, report.skipped, report.failed, report.duration,
        )
        return report