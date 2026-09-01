from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.config import Config, WorkspaceConfig, WorkspaceItem
from core.workspace import WorkspaceManager, DEFAULT_WORKSPACE_ID


@pytest.fixture
def ws_config(tmp_path: Path) -> Config:
    cfg = Config(
        files_dir=tmp_path / "files",
        chroma_dir=tmp_path / "chroma_db",
        sqlite_path=tmp_path / "kb.sqlite",
        logs_dir=tmp_path / "logs",
    )
    return cfg


@pytest.fixture
def ws_manager(ws_config: Config, tmp_path: Path) -> WorkspaceManager:
    data_root = tmp_path / "data"
    data_root.mkdir(exist_ok=True)
    mgr = WorkspaceManager(ws_config, data_root)
    mgr.ensure_default()
    return mgr


def test_default_workspace_exists(ws_manager: WorkspaceManager):
    ws = ws_manager.get_default()
    assert ws.id == DEFAULT_WORKSPACE_ID
    assert ws.chroma_dir.exists()
    assert ws.files_dir.exists()


def test_list_workspaces(ws_manager: WorkspaceManager):
    items = ws_manager.list_workspaces()
    assert len(items) == 1
    assert items[0].id == DEFAULT_WORKSPACE_ID


def test_create_workspace(ws_manager: WorkspaceManager):
    item = ws_manager.create("测试工作区")
    assert item.name == "测试工作区"
    assert item.id != DEFAULT_WORKSPACE_ID
    ws = ws_manager.get_workspace(item.id)
    assert ws is not None
    assert ws.chroma_dir.exists()
    assert ws.files_dir.exists()
    assert len(ws_manager.list_workspaces()) == 2


def test_switch_workspace(ws_manager: WorkspaceManager):
    item = ws_manager.create("新工作区")
    ws = ws_manager.switch(item.id)
    assert ws.id == item.id
    assert ws_manager.config.workspaces.current == item.id
    current = ws_manager.get_current()
    assert current.id == item.id


def test_switch_nonexistent(ws_manager: WorkspaceManager):
    with pytest.raises(ValueError, match="工作区不存在"):
        ws_manager.switch("nonexistent-id")


def test_delete_default_rejected(ws_manager: WorkspaceManager):
    with pytest.raises(ValueError, match="不能删除默认工作区"):
        ws_manager.delete(DEFAULT_WORKSPACE_ID)


def test_delete_archives_by_default(ws_manager: WorkspaceManager):
    item = ws_manager.create("待删除")
    ws_id = item.id
    ws_manager.delete(ws_id)
    assert ws_manager.get_workspace(ws_id) is None
    archived = ws_manager.list_archived()
    assert ws_id in archived


def test_delete_without_archive(ws_manager: WorkspaceManager):
    item = ws_manager.create("待删除")
    ws_id = item.id
    ws_manager.delete(ws_id, archive=False)
    assert ws_manager.get_workspace(ws_id) is None
    assert ws_id not in ws_manager.list_archived()


def test_restore_workspace(ws_manager: WorkspaceManager):
    item = ws_manager.create("待归档")
    ws_id = item.id
    ws_manager.delete(ws_id)
    restored = ws_manager.restore(ws_id)
    assert restored.id == ws_id
    assert ws_manager.get_workspace(ws_id) is not None


def test_restore_nonexistent(ws_manager: WorkspaceManager):
    with pytest.raises(ValueError, match="归档工作区不存在"):
        ws_manager.restore("nonexistent-id")


def test_delete_switches_to_default_if_current(ws_manager: WorkspaceManager):
    item = ws_manager.create("临时工作区")
    ws_manager.switch(item.id)
    assert ws_manager.config.workspaces.current == item.id
    ws_manager.delete(item.id)
    assert ws_manager.config.workspaces.current == DEFAULT_WORKSPACE_ID


def test_data_isolation(ws_manager: WorkspaceManager, tmp_path: Path):
    from core.metadata_manager import MetadataManager
    from core.vector_store import VectorStore

    ws_a = ws_manager.get_default()
    item_b = ws_manager.create("工作区B")
    ws_b = ws_manager.get_workspace(item_b.id)

    meta_a = MetadataManager(str(ws_a.sqlite_path), vector_store=VectorStore(str(ws_a.chroma_dir)))
    meta_b = MetadataManager(str(ws_b.sqlite_path), vector_store=VectorStore(str(ws_b.chroma_dir)))

    doc_a = meta_a.create_document("doc_a.txt", ".txt", 100, DEFAULT_WORKSPACE_ID)
    docs_b = meta_b.list_documents()

    assert all(d.id != doc_a for d in docs_b)


def test_legacy_migration(ws_config: Config, tmp_path: Path):
    data_root = tmp_path / "data"
    data_root.mkdir()

    (data_root / "chroma_db").mkdir()
    (data_root / "chroma_db" / "test.txt").write_text("vector data")
    (data_root / "kb.sqlite").write_text("sqlite data")
    (data_root / "files").mkdir()
    (data_root / "files" / "doc.txt").write_text("file content")

    mgr = WorkspaceManager(ws_config, data_root)
    migrated = mgr.migrate_legacy_data()

    assert migrated is True
    default_ws = mgr.get_default()
    assert (default_ws.chroma_dir / "test.txt").exists()
    assert default_ws.sqlite_path.exists()
    assert (default_ws.files_dir / "doc.txt").exists()
    assert not (data_root / "chroma_db").exists()
    assert not (data_root / "kb.sqlite").exists()


def test_legacy_migration_skips_if_already_migrated(ws_config: Config, tmp_path: Path):
    data_root = tmp_path / "data"
    data_root.mkdir()
    ws_root = data_root / "workspaces" / "default"
    ws_root.mkdir(parents=True)
    (ws_root / "chroma_db").mkdir()

    mgr = WorkspaceManager(ws_config, data_root)
    assert mgr.migrate_legacy_data() is False


def test_legacy_migration_skips_if_no_legacy(ws_config: Config, tmp_path: Path):
    data_root = tmp_path / "data"
    data_root.mkdir()

    mgr = WorkspaceManager(ws_config, data_root)
    assert mgr.migrate_legacy_data() is False


def test_workspace_config_validate():
    cfg = WorkspaceConfig(
        current="default",
        items=[WorkspaceItem(id="default", name="默认"), WorkspaceItem(id="ws1", name="WS1")],
    )
    assert cfg.validate() == []


def test_workspace_config_validate_duplicate_ids():
    cfg = WorkspaceConfig(
        current="default",
        items=[WorkspaceItem(id="default", name="A"), WorkspaceItem(id="default", name="B")],
    )
    errors = cfg.validate()
    assert any("unique" in e for e in errors)


def test_workspace_config_validate_empty_name():
    cfg = WorkspaceConfig(
        current="default",
        items=[WorkspaceItem(id="default", name="")],
    )
    errors = cfg.validate()
    assert any("empty" in e for e in errors)


def test_workspace_config_validate_current_not_found():
    cfg = WorkspaceConfig(
        current="missing",
        items=[WorkspaceItem(id="default", name="默认")],
    )
    errors = cfg.validate()
    assert any("not found" in e for e in errors)


def test_mcp_workspace_not_found(monkeypatch):
    import mcp_server.tools as tools

    tools.reset_services_cache()

    def mock_get_services(ws=None):
        return None

    monkeypatch.setattr(tools, "_get_services", mock_get_services)
    result = tools.search_knowledge_base("test", workspace="nonexistent")
    assert result == {"error": "workspace not found"}

    result = tools.list_knowledge_bases(workspace="nonexistent")
    assert result == {"error": "workspace not found"}

    result = tools.get_document_preview("doc1", workspace="nonexistent")
    assert result == {"error": "workspace not found"}