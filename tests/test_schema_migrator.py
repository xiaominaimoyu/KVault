from __future__ import annotations

import sqlite3
from pathlib import Path

from core.schema_migrator import CURRENT_SCHEMA_VERSION, SchemaMigrator


def test_migrate_creates_schema_meta(tmp_path: Path):
    db_path = tmp_path / "test.sqlite"
    migrator = SchemaMigrator(str(db_path))
    version = migrator.migrate()
    assert version == CURRENT_SCHEMA_VERSION

    with sqlite3.connect(str(db_path)) as conn:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    assert "schema_meta" in tables
    assert "index_meta" in tables


def test_migrate_idempotent(tmp_path: Path):
    db_path = tmp_path / "test.sqlite"
    migrator = SchemaMigrator(str(db_path))
    v1 = migrator.migrate()
    v2 = migrator.migrate()
    assert v1 == v2 == CURRENT_SCHEMA_VERSION


def test_migrate_from_old_schema(tmp_path: Path):
    db_path = tmp_path / "test.sqlite"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("CREATE TABLE documents (id TEXT PRIMARY KEY, file_name TEXT)")
        conn.execute("INSERT INTO documents VALUES ('d1', 'test.txt')")
        conn.commit()

    migrator = SchemaMigrator(str(db_path))
    version = migrator.migrate()
    assert version == CURRENT_SCHEMA_VERSION

    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute("SELECT value FROM schema_meta WHERE key='version'").fetchone()
        assert row is not None
        assert int(row[0]) == CURRENT_SCHEMA_VERSION
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "index_meta" in tables
        docs = conn.execute("SELECT id FROM documents").fetchall()
        assert len(docs) == 1


def test_migrate_creates_note_tables(tmp_path: Path):
    """v4 引入笔记库相关表。"""
    db_path = tmp_path / "test.sqlite"
    SchemaMigrator(str(db_path)).migrate()

    with sqlite3.connect(str(db_path)) as conn:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}

    assert "notes" in tables
    assert "note_links" in tables
    assert "note_tags" in tables


def test_note_tables_work_without_documents(tmp_path: Path):
    """documents 表不存在时建表也不应失败（外键需条件声明）。"""
    db_path = tmp_path / "test.sqlite"
    SchemaMigrator(str(db_path)).migrate()

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO notes (path, title) VALUES ('a.md', '甲')"
        )
        conn.commit()
        row = conn.execute("SELECT title FROM notes WHERE path='a.md'").fetchone()

    assert row[0] == "甲"
