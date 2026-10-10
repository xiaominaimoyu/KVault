"""笔记库（vault）与 RAG 索引的桥接层。

KVault 原本只把**导入的外部文件**存进平铺目录做检索，无法编辑、无法链接。
本模块把「笔记」接入既有流水线，同时保持分工清晰：

- :class:`~core.vault.Vault` 负责磁盘上的文件真相（增删改查、路径安全）
- 本模块负责 SQLite 中的**索引**：笔记元数据、链接边、标签，以及把笔记
  同步为可被向量检索命中的 ``documents`` 记录

关键设计：**笔记即文档**。每份笔记在 ``documents`` 中有一行，因此它自动
获得 KVault 已有的语义检索、混合检索、MCP 只读检索等全部能力，无需改动检索层。
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from core.frontmatter import parse as parse_frontmatter
from core.links import extract_links, extract_tags, tag_hierarchy
from core.metadata_manager import DEFAULT_PARTITION_ID, MetadataManager
from core.title import excerpt, title_from_content, word_count
from core.vault import Vault, VaultNote, normalize_rel_path

logger = logging.getLogger(__name__)

#: 笔记默认归属的分区名，用于在既有 UI 中可见
DEFAULT_NOTE_PARTITION = "笔记"


@dataclass
class NoteRecord:
    """SQLite 中的一条笔记索引记录。"""

    path: str
    title: str = ""
    document_id: str | None = None
    mtime: float = 0.0
    size: int = 0
    content_hash: str = ""
    word_count: int = 0
    created_at: float = 0.0
    updated_at: float = 0.0
    tags: list[str] = field(default_factory=list)
    """标签列表。**不落库**，由 :meth:`NoteStore.list_notes` 按需填充。"""

    @property
    def name(self) -> str:
        return self.path.rsplit("/", 1)[-1][: -len(".md")]

    @property
    def folder(self) -> str:
        return self.path.rsplit("/", 1)[0] if "/" in self.path else ""


@dataclass
class LinkRecord:
    """一条链接边。"""

    source_path: str
    target_path: str
    """链接原始目标文本。"""

    target_resolved: str | None = None
    """解析成功后的笔记路径；未解析时为 ``None``。"""

    kind: str = "link"
    heading: str | None = None
    alias: str | None = None
    context: str = ""
    line_no: int = 0

    @property
    def is_embed(self) -> bool:
        return self.kind == "embed"

    @property
    def is_broken(self) -> bool:
        return self.target_resolved is None


@dataclass
class SyncReport:
    """一次全量同步的结果统计。"""

    added: list[str] = None
    updated: list[str] = None
    removed: list[str] = None
    unchanged: int = 0
    dirty: list[str] = None

    def __post_init__(self):
        self.added = self.added or []
        self.updated = self.updated or []
        self.removed = self.removed or []
        self.dirty = self.dirty or []

    @property
    def changed(self) -> list[str]:
        """需要（重新）建立向量索引的笔记。"""
        return self.added + self.updated + self.dirty

    def as_dict(self) -> dict:
        return {
            "added": len(self.added),
            "updated": len(self.updated),
            "removed": len(self.removed),
            "unchanged": self.unchanged,
            "dirty": len(self.dirty),
        }


def content_hash(text: str) -> str:
    """计算笔记内容哈希，用于判断是否需要重建索引。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class NoteStore:
    """笔记的持久化与索引。

    :param db_path: SQLite 路径
    :param vault_root: vault 目录
    :param metadata: 既有 :class:`MetadataManager`，用于把笔记登记为可检索文档
    """

    def __init__(
        self,
        db_path: str,
        vault_root: str | Path,
        metadata: MetadataManager | None = None,
    ):
        self.db_path = str(db_path)
        self.vault = Vault(vault_root)
        self.metadata = metadata
        self._init_db()

    # ---------------------------------------------------------------- 内部

    def _conn(self) -> sqlite3.Connection:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        from core.schema_migrator import SchemaMigrator

        SchemaMigrator(self.db_path).migrate()

        # 复用迁移器创建的表结构；此处仅补齐独立使用时的兜底建表
        fk = (
            ",\n                    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE SET NULL"
            if self._documents_exists()
            else ""
        )

        with self._conn() as conn:
            conn.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS notes (
                    path TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    document_id TEXT,
                    mtime REAL DEFAULT 0,
                    size INTEGER DEFAULT 0,
                    content_hash TEXT,
                    word_count INTEGER DEFAULT 0,
                    created_at REAL,
                    updated_at REAL{fk}
                );
                CREATE TABLE IF NOT EXISTS note_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_path TEXT NOT NULL,
                    target_path TEXT NOT NULL,
                    target_resolved TEXT,
                    kind TEXT NOT NULL DEFAULT 'link',
                    heading TEXT,
                    alias TEXT,
                    context TEXT,
                    line_no INTEGER DEFAULT 0,
                    UNIQUE (source_path, target_path, heading, kind, line_no)
                );
                CREATE TABLE IF NOT EXISTS note_tags (
                    note_path TEXT NOT NULL,
                    tag TEXT NOT NULL,
                    origin TEXT NOT NULL DEFAULT 'inline',
                    PRIMARY KEY (note_path, tag)
                );
                CREATE INDEX IF NOT EXISTS idx_notes_title ON notes(title);
                CREATE INDEX IF NOT EXISTS idx_notes_updated ON notes(updated_at);
                CREATE INDEX IF NOT EXISTS idx_note_links_source ON note_links(source_path);
                CREATE INDEX IF NOT EXISTS idx_note_links_target ON note_links(target_resolved);
                CREATE INDEX IF NOT EXISTS idx_note_tags_tag ON note_tags(tag);
                """
            )

    def _documents_exists(self) -> bool:
        """既有 ``documents`` 表是否存在（决定能否声明外键）。"""
        if self.metadata is None:
            return False
        try:
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='documents'"
                ).fetchone()
            return row is not None
        except sqlite3.Error:
            return False

    # ---------------------------------------------------------------- 读取

    def get(self, rel_path: str) -> NoteRecord | None:
        """按路径查询笔记索引记录。"""
        rel = normalize_rel_path(rel_path)
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM notes WHERE path = ?", (rel,)).fetchone()
        return self._row_to_note(row) if row else None

    def list_notes(self, folder: str | None = None, keyword: str = "") -> list[NoteRecord]:
        """列出笔记，可按目录前缀与关键字过滤。"""
        sql = "SELECT * FROM notes"
        params: list = []
        clauses: list[str] = []
        if folder:
            clauses.append("(path = ? OR path LIKE ?)")
            params.extend([f"{folder}/%", f"{folder}/%"])
        if keyword:
            clauses.append("LOWER(title) LIKE ?")
            params.append(f"%{keyword.lower()}%")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY path"

        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()

        records = [self._row_to_note(row) for row in rows]
        self._attach_tags(records)
        return records

    def _attach_tags(self, records: list[NoteRecord]) -> None:
        """批量填充标签，避免逐条查询。"""
        if not records:
            return

        by_path = {record.path: record for record in records}
        placeholders = ",".join("?" * len(by_path))

        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT note_path, tag FROM note_tags WHERE note_path IN ({placeholders}) ORDER BY tag",
                list(by_path),
            ).fetchall()

        for row in rows:
            record = by_path.get(row["note_path"])
            if record is not None:
                record.tags.append(row["tag"])

    def read(self, rel_path: str) -> str:
        """读取笔记原文。"""
        return self.vault.read(rel_path)

    def note_and_content(self, rel_path: str) -> tuple[NoteRecord | None, str]:
        """一次性取回索引记录与原文，供编辑器加载。"""
        content = self.vault.read(rel_path)
        return self.get(rel_path), content

    # ---------------------------------------------------------------- 写入

    def create_note(
        self,
        title: str,
        folder: str = "",
        content: str = "",
        tags: list[str] | None = None,
        alias: str | None = None,
    ) -> str:
        """新建笔记并写入索引，返回相对路径。"""
        fm_text = _build_frontmatter(tags=tags, alias=alias)
        body = content if content else f"# {title}\n\n"
        text = f"{fm_text}\n{body}" if fm_text else body

        rel = self.vault.create(title, folder=folder, content=text)
        self.index_note(rel, text)
        return rel

    def save_note(
        self,
        rel_path: str,
        content: str,
        title: str | None = None,
        tags: list[str] | None = None,
    ) -> NoteRecord | None:
        """保存笔记内容。

        ``title`` 变化时同步重命名文件（并保持 ``.md`` 扩展名），
        ``tags`` 变化时写入 frontmatter。返回更新后的索引记录。
        """
        rel = normalize_rel_path(rel_path)

        if tags is not None:
            content = _apply_tags(content, tags)

        if title:
            desired = title.strip()
            current_stem = rel.rsplit("/", 1)[-1][: -len(".md")]
            if desired and desired != current_stem:
                rel = self.rename_note(rel, desired)

        self.vault.write(rel, content)
        return self.index_note(rel, content)

    def rename_note(self, rel_path: str, new_title: str) -> str:
        """重命名笔记并更新入链文本。

        保留原目录。与之相关的入链（``[[旧名]]``）会被改写为新名字，
        避免重命名后产生断链——这是 Obsidian「自动更新内部链接」的行为。
        """
        old = normalize_rel_path(rel_path)
        previous = self.get(old)
        new = self.vault.rename(old, new_title)

        if new != old:
            # 旧路径的索引必须一并清理，否则会留下指向已不存在文件的僵尸记录
            self._forget(old)
            if previous is not None:
                self._carry_over(new, previous)
            self._rewrite_inbound_links(old, new)

        return new

    def _carry_over(self, new_path: str, previous: NoteRecord) -> None:
        """重命名后把创建时间与文档 id 带到新路径，保持历史连续性。"""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO notes (path, title, document_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    created_at = excluded.created_at,
                    document_id = excluded.document_id
                """,
                (new_path, previous.title, previous.document_id, previous.created_at, time.time()),
            )

    def delete_note(self, rel_path: str, delete_file: bool = True) -> None:
        """删除笔记及其索引。若存在向量记录则一并清理。"""
        rel = normalize_rel_path(rel_path)
        record = self.get(rel)

        if self.metadata is not None and record and record.document_id:
            try:
                self.metadata.delete_document(record.document_id, delete_file=False)
            except Exception:  # noqa: BLE001 —— 索引清理失败不应阻塞文件删除
                logger.warning("清理笔记向量失败: %s", rel, exc_info=True)

        if delete_file:
            self.vault.delete(rel)
        self._forget(rel)
        # 目标消失后，指向它的链接应退回「未解析」状态
        self.reindex_links()

    # ---------------------------------------------------------------- 索引

    def index_note(
        self, rel_path: str, content: str, alias_map: dict[str, list[str]] | None = None
    ) -> NoteRecord:
        """把单份笔记的元数据、链接、标签写入索引。

        :param alias_map: ``路径 -> 别名`` 映射。批量同步时应传入，避免重复扫描磁盘。
        """
        rel = normalize_rel_path(rel_path)
        now = time.time()

        fm = parse_frontmatter(content)
        stat_info = self.vault.stat(rel)
        title = fm.title or title_from_content(content) or rel.rsplit("/", 1)[-1][: -len(".md")]

        existing = self.get(rel)
        created_at = existing.created_at if existing and existing.created_at else now
        document_id = existing.document_id if existing else None

        if self.metadata is not None:
            document_id = self._sync_document(rel, content, title, document_id, stat_info)

        record = NoteRecord(
            path=rel,
            title=title,
            document_id=document_id,
            mtime=stat_info.mtime if stat_info else 0.0,
            size=len(content.encode("utf-8")),
            content_hash=content_hash(content),
            word_count=word_count(content),
            created_at=created_at,
            updated_at=now,
        )

        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO notes
                    (path, title, document_id, mtime, size, content_hash,
                     word_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    title = excluded.title,
                    document_id = excluded.document_id,
                    mtime = excluded.mtime,
                    size = excluded.size,
                    content_hash = excluded.content_hash,
                    word_count = excluded.word_count,
                    updated_at = excluded.updated_at
                """,
                (
                    record.path,
                    record.title,
                    record.document_id,
                    record.mtime,
                    record.size,
                    record.content_hash,
                    record.word_count,
                    record.created_at,
                    record.updated_at,
                ),
            )

        self._index_links(rel, content, alias_map)
        self._index_tags(rel, fm, content)
        self._resolve_pending_links(rel)
        return record

    def _resolve_pending_links(self, rel_path: str) -> int:
        """新笔记出现后，把此前无法解析、且指向它的链接标记为已解析。

        Obsidian 允许先写 ``[[尚未创建]]`` 再补上笔记。这里用一条带条件的
        UPDATE 增量修复，避免每次创建都全量重建链接索引。
        """
        rel = normalize_rel_path(rel_path)
        stem = rel.rsplit("/", 1)[-1][: -len(".md")]

        with self._conn() as conn:
            cursor = conn.execute(
                """
                UPDATE note_links SET target_resolved = ?
                WHERE target_resolved IS NULL
                  AND (
                        LOWER(target_path) = ?
                     OR LOWER(target_path) = ?
                     OR LOWER(target_path) = ?
                     OR LOWER(target_path) = ?
                  )
                """,
                (rel, rel.lower(), stem.lower(), f"{stem}.md".lower(), stem.lower() + ".md"),
            )
            return cursor.rowcount or 0

    def sync_all(self) -> SyncReport:
        """全量同步：扫描 vault，把新增/变更/删除同步到索引。

        不会自动重建向量——需要重建的笔记列在报告的 ``changed`` 中，
        由调用方交给现有的 ingest 流水线处理。
        """
        report = SyncReport()
        on_disk = self.vault.iter_paths()
        known = {row["path"] for row in self._all_note_rows()}

        # 重建链接索引前先刷新别名，供链接解析使用
        alias_map = self._collect_aliases(on_disk)

        for rel in on_disk:
            try:
                content = self.vault.read(rel)
            except (OSError, UnicodeDecodeError):
                logger.warning("跳过无法读取的笔记: %s", rel)
                continue

            digest = content_hash(content)
            existing = self.get(rel)
            if existing and existing.content_hash == digest:
                report.unchanged += 1
                continue

            stat_info = self.vault.stat(rel)
            if (
                stat_info
                and existing
                and existing.mtime
                and stat_info.mtime > existing.mtime
                and digest == existing.content_hash
            ):
                report.unchanged += 1
                continue

            # 复用已算好的别名表，避免每篇笔记都重扫一遍磁盘
            self.index_note(rel, content, alias_map=alias_map)
            if existing is None:
                report.added.append(rel)
            else:
                report.updated.append(rel)
                report.dirty.append(rel)

        # 文件已被外部删除
        for rel in sorted(known - set(on_disk)):
            self._forget(rel)
            report.removed.append(rel)

        return report

    def reindex_links(self) -> int:
        """仅重建链接索引，不触碰笔记元数据。

        链接解析依赖全局别名表，因此一次全量重算比逐条更新更可靠。
        """
        paths = self.vault.iter_paths()
        alias_map = self._collect_aliases(paths)
        total = 0
        for rel in paths:
            try:
                content = self.vault.read(rel)
            except (OSError, UnicodeDecodeError):
                continue
            self._index_links(rel, content, alias_map)
            total += 1
        return total

    # ---------------------------------------------------------------- 链接

    def backlinks(self, rel_path: str) -> list[LinkRecord]:
        """返回指向该笔记的所有链接。"""
        rel = normalize_rel_path(rel_path)
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM note_links WHERE target_resolved = ? ORDER BY source_path",
                (rel,),
            ).fetchall()
        return [self._row_to_link(row) for row in rows]

    def outgoing_links(self, rel_path: str) -> list[LinkRecord]:
        """返回该笔记发出的所有链接。"""
        rel = normalize_rel_path(rel_path)
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM note_links WHERE source_path = ? ORDER BY id",
                (rel,),
            ).fetchall()
        return [self._row_to_link(row) for row in rows]

    def broken_links(self) -> list[LinkRecord]:
        """返回所有无法解析的链接，用于「修复断链」功能。"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM note_links WHERE target_resolved IS NULL "
                "ORDER BY target_path, source_path"
            ).fetchall()
        return [self._row_to_link(row) for row in rows]

    def orphan_notes(self) -> list[str]:
        """没有任何入链也没有出链的笔记。"""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT n.path FROM notes n
                WHERE n.path NOT IN (SELECT source_path FROM note_links)
                  AND n.path NOT IN (SELECT target_resolved FROM note_links)
                ORDER BY n.path
                """
            ).fetchall()
        return [row["path"] for row in rows]

    def linked_notes(self) -> dict[str, list[str]]:
        """返回 ``源笔记 -> [目标笔记]`` 的邻接表，供图谱视图使用。"""
        graph: dict[str, list[str]] = {}
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT source_path, target_resolved FROM note_links "
                "WHERE target_resolved IS NOT NULL ORDER BY id"
            ).fetchall()
        for row in rows:
            graph.setdefault(row["source_path"], [])
            if row["target_resolved"] not in graph[row["source_path"]]:
                graph[row["source_path"]].append(row["target_resolved"])
        return graph

    # ---------------------------------------------------------------- 标签

    def tags_for(self, rel_path: str) -> list[str]:
        """返回笔记的全部标签。"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT tag FROM note_tags WHERE note_path = ? ORDER BY tag",
                (normalize_rel_path(rel_path),),
            ).fetchall()
        return [row["tag"] for row in rows]

    def list_tags(self, include_parents: bool = True) -> dict[str, int]:
        """返回标签到笔记数的映射，可展开父子层级。"""
        with self._conn() as conn:
            rows = conn.execute("SELECT DISTINCT tag FROM note_tags").fetchall()
        names = [row["tag"] for row in rows]
        if include_parents:
            return tag_hierarchy(names)
        counts: dict[str, int] = {}
        for name in names:
            counts[name] = counts.get(name, 0) + 1
        return counts

    def notes_with_tag(self, tag: str) -> list[str]:
        """返回带指定标签的笔记。

        ``#项目`` 会同时命中 ``#项目/子项``，与 Obsidian 的层级标签语义一致。
        """
        prefix = tag.lstrip("#").strip()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT note_path FROM note_tags WHERE tag = ? OR tag LIKE ? ORDER BY note_path",
                (prefix, f"{prefix}/%"),
            ).fetchall()
        return [row["note_path"] for row in rows]

    # ---------------------------------------------------------------- 统计

    def stats(self) -> dict:
        """返回笔记库统计信息。"""
        with self._conn() as conn:
            note_count = conn.execute("SELECT COUNT(*) AS c FROM notes").fetchone()["c"]
            link_count = conn.execute("SELECT COUNT(*) AS c FROM note_links").fetchone()["c"]
            broken = conn.execute(
                "SELECT COUNT(*) AS c FROM note_links WHERE target_resolved IS NULL"
            ).fetchone()["c"]
            tag_count = conn.execute("SELECT COUNT(DISTINCT tag) AS c FROM note_tags").fetchone()["c"]
            words = conn.execute("SELECT COALESCE(SUM(word_count), 0) AS s FROM notes").fetchone()["s"]

        return {
            "notes": note_count,
            "links": link_count,
            "broken_links": broken,
            "tags": tag_count,
            "words": words,
        }

    # ---------------------------------------------------------------- 私有

    def _all_note_rows(self) -> list[sqlite3.Row]:
        with self._conn() as conn:
            return conn.execute("SELECT path FROM notes").fetchall()

    def _collect_aliases(self, paths: list[str]) -> dict[str, list[str]]:
        """扫描全部笔记，收集 ``路径 -> 别名``，用于链接解析。"""
        aliases: dict[str, list[str]] = {}
        for rel in paths:
            try:
                content = self.vault.read(rel)
            except (OSError, UnicodeDecodeError):
                continue
            fm = parse_frontmatter(content)
            if fm.aliases:
                aliases[rel] = fm.aliases
        return aliases

    def _index_links(self, rel_path: str, content: str, alias_map: dict[str, list[str]] | None = None) -> int:
        """重建单份笔记的链接记录。"""

        rel = normalize_rel_path(rel_path)

        # 链接解析需要全局视图：文件名、别名、标题
        if alias_map is None:
            alias_map = self._collect_aliases(self.vault.iter_paths())

        index = self.vault.reindex(alias_map)

        with self._conn() as conn:
            conn.execute("DELETE FROM note_links WHERE source_path = ?", (rel,))

            body = parse_frontmatter(content).body
            lines = body.split("\n")
            inserted = 0

            for link in extract_links(body):
                resolved = index.resolve(link.target, rel)
                line_no = body.count("\n", 0, link.start) + 1
                context = _line_context(lines, line_no)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO note_links
                        (source_path, target_path, target_resolved, kind, heading, alias, context, line_no)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rel,
                        link.target,
                        resolved,
                        "embed" if link.embed else "link",
                        link.heading,
                        link.alias,
                        context,
                        line_no,
                    ),
                )
                inserted += 1

        return inserted

    def _index_tags(self, rel_path: str, fm, content: str) -> int:
        """重建单份笔记的标签记录。"""
        rel = normalize_rel_path(rel_path)
        body = parse_frontmatter(content).body

        rows: list[tuple[str, str, str]] = [
            (rel, tag, "frontmatter") for tag in fm.tags
        ]
        seen = {tag for tag in fm.tags}
        for ref in extract_tags(body):
            if ref.name not in seen:
                seen.add(ref.name)
                rows.append((rel, ref.name, "inline"))

        with self._conn() as conn:
            conn.execute("DELETE FROM note_tags WHERE note_path = ?", (rel,))
            conn.executemany(
                "INSERT OR IGNORE INTO note_tags (note_path, tag, origin) VALUES (?, ?, ?)",
                rows,
            )
        return len(rows)

    def _forget(self, rel_path: str) -> None:
        """从索引中移除笔记（不删除文件）。"""
        rel = normalize_rel_path(rel_path)
        with self._conn() as conn:
            conn.execute("DELETE FROM notes WHERE path = ?", (rel,))
            conn.execute("DELETE FROM note_links WHERE source_path = ?", (rel,))
            conn.execute("DELETE FROM note_tags WHERE note_path = ?", (rel,))

    def _rewrite_inbound_links(self, old_path: str, new_path: str) -> None:
        """重命名后，把指向旧名的入链改写为新名。"""
        old_stem = old_path.rsplit("/", 1)[-1][: -len(".md")]
        new_stem = new_path.rsplit("/", 1)[-1][: -len(".md")]
        if not old_stem or not new_stem:
            return

        sources = self.backlinks(old_path)
        if not sources:
            return

        old_target = old_stem
        new_target = new_stem

        for record in sources:
            if record.target_path != old_target:
                continue
            try:
                content = self.vault.read(record.source_path)
            except OSError:
                continue

            updated = content.replace(f"[[{old_target}", f"[[{new_target}")
            if updated == content:
                continue
            self.vault.write(record.source_path, updated)
            self.index_note(record.source_path, updated)
            logger.info("已更新入链: %s -> %s", record.source_path, new_target)

        # 解析结果随重命名失效，触发一次链接重建
        self.reindex_links()

    def _sync_document(
        self,
        rel: str,
        content: str,
        title: str,
        document_id: str | None,
        stat_info: VaultNote | None,
    ) -> str | None:
        """把笔记登记为可检索文档，使既有 RAG 流水线能命中它。

        这里只负责元数据登记（``documents`` / ``chunks`` 表），
        真正的向量化仍由 :mod:`core.ingest` 完成。
        """
        if self.metadata is None:
            return document_id

        try:
            partition_id = self._note_partition()
            stored_path = str(self.vault.abspath(rel))

            if document_id:
                self.metadata.update_status(document_id, "pending")
                # 原地更新内容哈希与元信息，不新建记录
                with self.metadata._conn() as conn:  # noqa: SLF001 —— 复用既有连接工厂
                    conn.execute(
                        "UPDATE documents SET file_name = ?, file_ext = ?, file_size = ?, "
                        "stored_path = ?, partition_id = ?, original_path = ? WHERE id = ?",
                        (
                            rel.rsplit("/", 1)[-1],
                            ".md",
                            stat_info.size if stat_info else 0,
                            stored_path,
                            partition_id,
                            stored_path,
                            document_id,
                        ),
                    )
                    conn.execute(
                        "UPDATE documents SET content_hash = ?, mtime = ? WHERE id = ?",
                        (
                            content_hash(content),
                            stat_info.mtime if stat_info else 0.0,
                            document_id,
                        ),
                    )
                self.metadata.clear_chunks(document_id)
                return document_id

            new_id = self.metadata.create_document(
                file_name=rel.rsplit("/", 1)[-1],
                stored_path=stored_path,
                file_ext=".md",
                file_size=stat_info.size if stat_info else 0,
                original_path=stored_path,
                partition_id=partition_id,
            )
            with self.metadata._conn() as conn:  # noqa: SLF001
                conn.execute(
                    "UPDATE documents SET content_hash = ?, mtime = ? WHERE id = ?",
                    (content_hash(content), stat_info.mtime if stat_info else 0.0, new_id),
                )
            return new_id
        except Exception:  # noqa: BLE001 —— 索引失败不应阻断文件写入
            logger.warning("同步笔记到文档索引失败: %s", rel, exc_info=True)
            return document_id

    def _note_partition(self) -> str:
        """获取（或创建）笔记专用分区。"""
        for row in self.metadata.list_partitions():
            if row["name"] == DEFAULT_NOTE_PARTITION:
                return row["id"]
        try:
            return self.metadata.create_partition(DEFAULT_NOTE_PARTITION)
        except ValueError:
            return DEFAULT_PARTITION_ID

    @staticmethod
    def _row_to_note(row: sqlite3.Row) -> NoteRecord:
        return NoteRecord(
            path=row["path"],
            title=row["title"] or "",
            document_id=row["document_id"],
            mtime=row["mtime"] or 0.0,
            size=row["size"] or 0,
            content_hash=row["content_hash"] or "",
            word_count=row["word_count"] or 0,
            created_at=row["created_at"] or 0.0,
            updated_at=row["updated_at"] or 0.0,
        )

    @staticmethod
    def _row_to_link(row: sqlite3.Row) -> LinkRecord:
        return LinkRecord(
            source_path=row["source_path"],
            target_path=row["target_path"],
            target_resolved=row["target_resolved"],
            kind=row["kind"],
            heading=row["heading"],
            alias=row["alias"],
            context=row["context"] or "",
            line_no=row["line_no"] or 0,
        )


# --------------------------------------------------------------------------
# 辅助
# --------------------------------------------------------------------------


def _line_context(lines: list[str], line_no: int, width: int = 160) -> str:
    """取链接所在行的上下文，用于反链列表展示。"""
    if line_no < 1 or line_no > len(lines):
        return ""
    text = lines[line_no - 1].strip()
    return text if len(text) <= width else text[: width - 1] + "…"


def _build_frontmatter(tags: list[str] | None, alias: str | None) -> str:
    """生成新笔记的 frontmatter 片段。"""
    from core import frontmatter as fm

    data: dict = {}
    if tags:
        data["tags"] = [t.lstrip("#").strip() for t in tags if str(t).strip()]
    if alias:
        data["aliases"] = [alias.strip()]
    if not data:
        return ""
    return fm.dump(data, "")


def _apply_tags(content: str, tags: list[str]) -> str:
    """把标签合并进笔记 frontmatter。"""
    from core.frontmatter import ensure_tags

    cleaned = [str(t).lstrip("#").strip() for t in tags if str(t).strip()]
    return ensure_tags(content, cleaned)


def preview_of(content: str, length: int = 160) -> str:
    """生成笔记摘要文本，供列表展示。"""
    return excerpt(content, length=length)


def iso_now() -> str:
    """当前时间的 ISO 字符串，用于写入 frontmatter。"""
    return datetime.now().isoformat(timespec="seconds")