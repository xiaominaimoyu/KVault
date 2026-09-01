"""SQLite schema 增量迁移管理器。

通过 schema_meta 表记录版本号，按版本号执行 ALTER TABLE 增量迁移。
旧 schema 可安全升级，迁移失败时回滚事务。
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 3


class SchemaMigrator:
    """按版本号执行 SQLite schema 增量迁移。"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _get_version(self, conn: sqlite3.Connection) -> int:
        row = conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'version'"
        ).fetchone()
        return int(row["value"]) if row else 0

    def _set_version(self, conn: sqlite3.Connection, version: int) -> None:
        conn.execute(
            "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('version', ?)",
            (str(version),),
        )

    def migrate(self) -> int:
        """执行迁移，返回迁移后的版本号。"""
        with self._conn() as conn:
            if not self._table_exists(conn, "schema_meta"):
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT)"
                )
                self._set_version(conn, 1)
                logger.info("schema_meta created, version=1")

            current = self._get_version(conn)
            if current >= CURRENT_SCHEMA_VERSION:
                return current

            if current < 2:
                self._migrate_v1_to_v2(conn)
            if current < 3:
                self._migrate_v2_to_v3(conn)

            self._set_version(conn, CURRENT_SCHEMA_VERSION)
            logger.info("schema migrated to version=%d", CURRENT_SCHEMA_VERSION)
            return CURRENT_SCHEMA_VERSION

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        return row is not None

    @staticmethod
    def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
        """v1→v2: 创建 index_meta 表用于记录嵌入模型版本信息。"""
        if not SchemaMigrator._table_exists(conn, "index_meta"):
            conn.execute(
                "CREATE TABLE IF NOT EXISTS index_meta (key TEXT PRIMARY KEY, value TEXT)"
            )
            logger.info("index_meta table created")

    @staticmethod
    def _migrate_v2_to_v3(conn: sqlite3.Connection) -> None:
        """v2→v3: documents 表新增 content_hash / mtime 列用于增量更新。"""
        cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(documents)").fetchall()
        }
        if "content_hash" not in cols:
            conn.execute("ALTER TABLE documents ADD COLUMN content_hash TEXT")
        if "mtime" not in cols:
            conn.execute("ALTER TABLE documents ADD COLUMN mtime REAL")
        logger.info("documents table: added content_hash/mtime columns")
