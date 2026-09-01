import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DEFAULT_PARTITION_NAME = "全部文档"
DEFAULT_PARTITION_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "kvault.partition.default").hex
DEFAULT_PARTITIONS = [DEFAULT_PARTITION_NAME, "技术笔记", "项目资料", "阅读笔记", "灵感收藏"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    file_name TEXT NOT NULL,
    original_path TEXT,
    stored_path TEXT NOT NULL,
    file_ext TEXT,
    file_size INTEGER DEFAULT 0,
    partition_id TEXT,
    status TEXT DEFAULT 'pending',
    chunk_count INTEGER DEFAULT 0,
    error_message TEXT,
    created_at REAL,
    updated_at REAL
);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content_preview TEXT,
    token_count INTEGER DEFAULT 0,
    chroma_id TEXT NOT NULL,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS partitions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS tags (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS document_tags (
    document_id TEXT NOT NULL,
    tag_id TEXT NOT NULL,
    PRIMARY KEY (document_id, tag_id),
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_partition ON documents(partition_id);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
"""


@dataclass
class Document:
    id: str
    file_name: str
    original_path: str
    stored_path: str
    file_ext: str
    file_size: int
    partition_id: Optional[str]
    partition_name: Optional[str]
    status: str
    chunk_count: int
    error_message: Optional[str]
    created_at: float
    updated_at: float


class MetadataManager:
    def __init__(self, db_path: str, vector_store=None):
        self.db_path = db_path
        self.vector_store = vector_store
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript(SCHEMA)
            self._ensure_default_partitions(conn)

    def _ensure_default_partitions(self, conn: sqlite3.Connection):
        name_to_id: dict[str, str] = {DEFAULT_PARTITION_NAME: DEFAULT_PARTITION_ID}
        for name in DEFAULT_PARTITIONS:
            if name == DEFAULT_PARTITION_NAME:
                pid = DEFAULT_PARTITION_ID
            else:
                pid = uuid.uuid5(uuid.NAMESPACE_DNS, f"kvault.partition.{name}").hex
            name_to_id[name] = pid

            existing = conn.execute(
                "SELECT id FROM partitions WHERE name = ?", (name,)
            ).fetchone()
            if existing:
                old_id = existing["id"]
                if old_id != pid:
                    conn.execute(
                        "UPDATE documents SET partition_id = ? WHERE partition_id = ?",
                        (pid, old_id),
                    )
                    conn.execute(
                        "UPDATE partitions SET id = ? WHERE id = ?",
                        (pid, old_id),
                    )
            else:
                conn.execute(
                    "INSERT INTO partitions (id, name) VALUES (?, ?)",
                    (pid, name),
                )

        # Migrate any documents whose partition_id still equals an old partition name
        for name, pid in name_to_id.items():
            conn.execute(
                "UPDATE documents SET partition_id = ? WHERE partition_id = ?",
                (pid, name),
            )

    def create_document(
        self,
        file_name: str,
        stored_path: str,
        file_ext: str,
        file_size: int,
        original_path: str = "",
        partition_id: str = DEFAULT_PARTITION_ID,
    ) -> str:
        doc_id = uuid.uuid4().hex
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO documents
                (id, file_name, original_path, stored_path, file_ext, file_size,
                 partition_id, status, chunk_count, error_message, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id,
                    file_name,
                    original_path,
                    stored_path,
                    file_ext,
                    file_size,
                    partition_id,
                    "pending",
                    0,
                    None,
                    now,
                    now,
                ),
            )
        return doc_id

    def update_status(
        self,
        doc_id: str,
        status: str,
        error_message: Optional[str] = None,
        chunk_count: Optional[int] = None,
    ):
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE documents
                SET status = ?, error_message = COALESCE(?, error_message),
                    chunk_count = COALESCE(?, chunk_count), updated_at = ?
                WHERE id = ?
                """,
                (status, error_message, chunk_count, now, doc_id),
            )

    def update_partition(self, doc_id: str, partition_id: str):
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                "UPDATE documents SET partition_id = ?, updated_at = ? WHERE id = ?",
                (partition_id, now, doc_id),
            )

    def add_chunks(self, doc_id: str, chunks: list[tuple[int, str, str]]):
        """Save chunk metadata: (chunk_index, content_preview, chroma_id)."""
        now = time.time()
        rows = [
            (f"{doc_id}_{chunk_index}", doc_id, chunk_index, preview, chroma_id)
            for chunk_index, preview, chroma_id in chunks
        ]
        with self._conn() as conn:
            if rows:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO chunks
                    (id, document_id, chunk_index, content_preview, chroma_id)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    rows,
                )
            conn.execute(
                "UPDATE documents SET updated_at = ? WHERE id = ?",
                (now, doc_id),
            )

    def clear_chunks(self, doc_id: str):
        """清空文档的 chunk 记录（重新索引前调用）。"""
        with self._conn() as conn:
            conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))

    def list_documents(
        self,
        partition_id: Optional[str] = None,
        tag_ids: Optional[list[str]] = None,
        keyword: Optional[str] = None,
    ) -> list[Document]:
        conditions = []
        args: list = []

        if partition_id:
            conditions.append("d.partition_id = ?")
            args.append(partition_id)

        if tag_ids:
            placeholders = ",".join("?" * len(tag_ids))
            conditions.append(
                f"d.id IN (SELECT document_id FROM document_tags WHERE tag_id IN ({placeholders}))"
            )
            args.extend(tag_ids)

        if keyword:
            conditions.append(
                "(LOWER(d.file_name) LIKE ? OR LOWER(d.file_ext) LIKE ? OR LOWER(COALESCE(p.name, '')) LIKE ?)"
            )
            like = f"%{keyword.lower()}%"
            args.extend([like, like, like])

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"""
            SELECT d.*, p.name as partition_name
            FROM documents d
            LEFT JOIN partitions p ON d.partition_id = p.id
            {where}
            ORDER BY d.created_at DESC
        """

        with self._conn() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [self._row_to_doc(row) for row in rows]

    def get_document(self, doc_id: str) -> Optional[Document]:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT d.*, p.name as partition_name
                FROM documents d
                LEFT JOIN partitions p ON d.partition_id = p.id
                WHERE d.id = ?
                """,
                (doc_id,),
            ).fetchone()
        return self._row_to_doc(row) if row else None

    def get_document_by_stored_path(self, stored_path: str) -> Optional[Document]:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT d.*, p.name as partition_name
                FROM documents d
                LEFT JOIN partitions p ON d.partition_id = p.id
                WHERE d.stored_path = ?
                """,
                (stored_path,),
            ).fetchone()
        return self._row_to_doc(row) if row else None

    def get_document_chunks(self, doc_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT chunk_index, content_preview, chroma_id
                FROM chunks WHERE document_id = ? ORDER BY chunk_index
                """,
                (doc_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_document(self, doc_id: str, delete_file: bool = False):
        doc = self.get_document(doc_id)
        if self.vector_store:
            self.vector_store.delete_by_document(doc_id)
        with self._conn() as conn:
            conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
            conn.execute("DELETE FROM document_tags WHERE document_id = ?", (doc_id,))
            conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        if delete_file and doc and Path(doc.stored_path).exists():
            Path(doc.stored_path).unlink()

    # ---------- 分区管理 ----------

    def create_partition(self, name: str) -> str:
        pid = uuid.uuid4().hex
        try:
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO partitions (id, name) VALUES (?, ?)",
                    (pid, name),
                )
        except sqlite3.IntegrityError as e:
            raise ValueError(f"Partition name already exists: {name}") from e
        return pid

    def rename_partition(self, partition_id: str, new_name: str):
        try:
            with self._conn() as conn:
                conn.execute(
                    "UPDATE partitions SET name = ? WHERE id = ?",
                    (new_name, partition_id),
                )
        except sqlite3.IntegrityError as e:
            raise ValueError(f"Partition name already exists: {new_name}") from e

    def delete_partition(
        self,
        partition_id: str,
        target_partition_id: str = DEFAULT_PARTITION_ID,
    ):
        if partition_id == DEFAULT_PARTITION_ID:
            raise ValueError("Cannot delete the default partition")
        if partition_id == target_partition_id:
            raise ValueError("Target partition must differ from the deleted partition")
        with self._conn() as conn:
            conn.execute(
                "UPDATE documents SET partition_id = ? WHERE partition_id = ?",
                (target_partition_id, partition_id),
            )
            conn.execute(
                "DELETE FROM partitions WHERE id = ?",
                (partition_id,),
            )

    def list_partitions(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT id, name FROM partitions ORDER BY name").fetchall()
        return [dict(row) for row in rows]

    def list_partitions_with_counts(self) -> list[dict]:
        sql = """
        SELECT p.id, p.name, COUNT(d.id) as doc_count
        FROM partitions p
        LEFT JOIN documents d ON d.partition_id = p.id
        GROUP BY p.id, p.name
        ORDER BY p.name
        """
        with self._conn() as conn:
            rows = conn.execute(sql).fetchall()
        return [dict(row) for row in rows]

    def get_partition(self, partition_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, name FROM partitions WHERE id = ?", (partition_id,)
            ).fetchone()
        return dict(row) if row else None

    # ---------- 标签管理 ----------

    def create_tag(self, name: str) -> str:
        tag_id = uuid.uuid4().hex
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO tags (id, name) VALUES (?, ?)",
                (tag_id, name),
            )
            row = conn.execute(
                "SELECT id FROM tags WHERE name = ?", (name,)
            ).fetchone()
        return row["id"] if row else tag_id

    def rename_tag(self, tag_id: str, new_name: str):
        try:
            with self._conn() as conn:
                conn.execute(
                    "UPDATE tags SET name = ? WHERE id = ?",
                    (new_name, tag_id),
                )
        except sqlite3.IntegrityError as e:
            raise ValueError(f"Tag name already exists: {new_name}") from e

    def delete_tag(self, tag_id: str):
        with self._conn() as conn:
            conn.execute("DELETE FROM document_tags WHERE tag_id = ?", (tag_id,))
            conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))

    def list_tags(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT id, name FROM tags ORDER BY name").fetchall()
        return [dict(row) for row in rows]

    def list_tags_with_counts(self) -> list[dict]:
        sql = """
        SELECT t.id, t.name, COUNT(dt.document_id) as doc_count
        FROM tags t
        LEFT JOIN document_tags dt ON dt.tag_id = t.id
        GROUP BY t.id, t.name
        ORDER BY name
        """
        with self._conn() as conn:
            rows = conn.execute(sql).fetchall()
        return [dict(row) for row in rows]

    def add_document_tags(self, doc_id: str, tag_ids: list[str]):
        if not tag_ids:
            return
        with self._conn() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO document_tags (document_id, tag_id) VALUES (?, ?)",
                [(doc_id, tag_id) for tag_id in tag_ids],
            )

    def remove_document_tags(self, doc_id: str, tag_ids: list[str]):
        if not tag_ids:
            return
        placeholders = ",".join("?" * len(tag_ids))
        with self._conn() as conn:
            conn.execute(
                f"DELETE FROM document_tags WHERE document_id = ? AND tag_id IN ({placeholders})",
                (doc_id, *tag_ids),
            )

    def set_document_tags(self, doc_id: str, tag_ids: list[str]):
        with self._conn() as conn:
            conn.execute("DELETE FROM document_tags WHERE document_id = ?", (doc_id,))
            if tag_ids:
                conn.executemany(
                    "INSERT OR IGNORE INTO document_tags (document_id, tag_id) VALUES (?, ?)",
                    [(doc_id, tag_id) for tag_id in tag_ids],
                )

    def get_document_tags(self, doc_id: str) -> list[dict]:
        sql = """
        SELECT t.id, t.name
        FROM tags t
        JOIN document_tags dt ON dt.tag_id = t.id
        WHERE dt.document_id = ?
        ORDER BY t.name
        """
        with self._conn() as conn:
            rows = conn.execute(sql, (doc_id,)).fetchall()
        return [dict(row) for row in rows]


    def get_documents_tag_map(self, doc_ids: list[str]) -> dict[str, list[dict]]:
        result: dict[str, list[dict]] = {doc_id: [] for doc_id in doc_ids}
        if not doc_ids:
            return result
        placeholders = ",".join("?" * len(doc_ids))
        sql = f"""
        SELECT dt.document_id, t.id, t.name
        FROM document_tags dt
        JOIN tags t ON t.id = dt.tag_id
        WHERE dt.document_id IN ({placeholders})
        ORDER BY t.name
        """
        with self._conn() as conn:
            rows = conn.execute(sql, doc_ids).fetchall()
        for row in rows:
            result[row["document_id"]].append({"id": row["id"], "name": row["name"]})
        return result

    # ---------- 统计 ----------

    def get_stats(self) -> dict:
        sql = """
        SELECT
            (SELECT COUNT(*) FROM documents) as total_docs,
            (SELECT COUNT(*) FROM documents WHERE status = 'indexed') as indexed_docs,
            (SELECT COUNT(*) FROM documents WHERE status = 'failed') as failed_docs,
            (SELECT COUNT(*) FROM chunks) as total_chunks,
            (SELECT COUNT(*) FROM partitions) as partition_count,
            (SELECT COUNT(*) FROM tags) as tag_count
        """
        with self._conn() as conn:
            row = conn.execute(sql).fetchone()
        return dict(row)

    def _row_to_doc(self, row: sqlite3.Row) -> Document:
        return Document(
            id=row["id"],
            file_name=row["file_name"],
            original_path=row["original_path"] or "",
            stored_path=row["stored_path"],
            file_ext=row["file_ext"] or "",
            file_size=row["file_size"] or 0,
            partition_id=row["partition_id"],
            partition_name=row["partition_name"] if "partition_name" in row.keys() else None,
            status=row["status"],
            chunk_count=row["chunk_count"] or 0,
            error_message=row["error_message"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
