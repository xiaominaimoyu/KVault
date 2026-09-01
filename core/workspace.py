"""多知识库工作区管理。

每个工作区拥有独立的 ChromaDB、SQLite 和文件目录，实现数据完全隔离。
工作区目录布局：data/workspaces/<ws_id>/{chroma_db, kb.sqlite, files}
归档目录：data/workspaces/_archived/<ws_id>/
"""

from __future__ import annotations

import logging
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from core.config import Config, WorkspaceConfig, WorkspaceItem

logger = logging.getLogger(__name__)

ARCHIVED_DIR_NAME = "_archived"
DEFAULT_WORKSPACE_ID = "default"


@dataclass
class Workspace:
    """工作区实例，包含解析后的路径。"""

    id: str
    name: str
    base_dir: Path
    chroma_dir: Path
    sqlite_path: Path
    files_dir: Path

    @classmethod
    def from_root(cls, ws_id: str, name: str, root: Path) -> "Workspace":
        base = root / ws_id
        return cls(
            id=ws_id,
            name=name,
            base_dir=base,
            chroma_dir=base / "chroma_db",
            sqlite_path=base / "kb.sqlite",
            files_dir=base / "files",
        )


class WorkspaceManager:
    """工作区管理器，负责创建、切换、删除、归档与恢复。"""

    def __init__(self, config: Config, data_root: Path):
        self._config = config
        self._data_root = data_root
        self._workspaces_root = data_root / "workspaces"
        self._workspaces_root.mkdir(parents=True, exist_ok=True)

    @property
    def workspaces_root(self) -> Path:
        return self._workspaces_root

    @property
    def config(self) -> Config:
        return self._config

    def list_workspaces(self) -> list[WorkspaceItem]:
        return list(self._config.workspaces.items)

    def list_archived(self) -> list[str]:
        archived = self._archived_dir()
        if not archived.exists():
            return []
        return [d.name for d in archived.iterdir() if d.is_dir()]

    def get_current(self) -> Workspace:
        ws_id = self._config.workspaces.current
        item = self._config.workspaces.get_item(ws_id)
        name = item.name if item else ws_id
        return Workspace.from_root(ws_id, name, self._workspaces_root)

    def get_default(self) -> Workspace:
        item = self._config.workspaces.get_item(DEFAULT_WORKSPACE_ID)
        name = item.name if item else "默认工作区"
        return Workspace.from_root(DEFAULT_WORKSPACE_ID, name, self._workspaces_root)

    def get_workspace(self, ws_id: str) -> Workspace | None:
        item = self._config.workspaces.get_item(ws_id)
        if item is None:
            return None
        return Workspace.from_root(ws_id, item.name, self._workspaces_root)

    def create(self, name: str) -> WorkspaceItem:
        ws_id = uuid.uuid4().hex[:12]
        while self._config.workspaces.get_item(ws_id) is not None:
            ws_id = uuid.uuid4().hex[:12]
        item = WorkspaceItem(id=ws_id, name=name)
        ws = Workspace.from_root(ws_id, name, self._workspaces_root)
        ws.chroma_dir.mkdir(parents=True, exist_ok=True)
        ws.files_dir.mkdir(parents=True, exist_ok=True)
        ws.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._config.workspaces.items.append(item)
        logger.info("创建工作区: %s (%s)", name, ws_id)
        return item

    def switch(self, workspace_id: str) -> Workspace:
        if self._config.workspaces.get_item(workspace_id) is None:
            raise ValueError(f"工作区不存在: {workspace_id}")
        self._config.workspaces.current = workspace_id
        ws = self.get_current()
        ws.chroma_dir.mkdir(parents=True, exist_ok=True)
        ws.files_dir.mkdir(parents=True, exist_ok=True)
        ws.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("切换到工作区: %s", workspace_id)
        return ws

    def delete(self, workspace_id: str, archive: bool = True) -> None:
        if workspace_id == DEFAULT_WORKSPACE_ID:
            raise ValueError("不能删除默认工作区")
        item = self._config.workspaces.get_item(workspace_id)
        if item is None:
            raise ValueError(f"工作区不存在: {workspace_id}")
        ws = Workspace.from_root(workspace_id, item.name, self._workspaces_root)
        if archive:
            archived_ws = self._archived_dir() / workspace_id
            archived_ws.parent.mkdir(parents=True, exist_ok=True)
            if archived_ws.exists():
                shutil.rmtree(archived_ws, ignore_errors=True)
            if ws.base_dir.exists():
                shutil.move(str(ws.base_dir), str(archived_ws))
            logger.info("归档工作区: %s -> %s", workspace_id, archived_ws)
        else:
            if ws.base_dir.exists():
                shutil.rmtree(ws.base_dir, ignore_errors=True)
            logger.info("删除工作区: %s", workspace_id)
        self._config.workspaces.items = [
            i for i in self._config.workspaces.items if i.id != workspace_id
        ]
        if self._config.workspaces.current == workspace_id:
            self._config.workspaces.current = DEFAULT_WORKSPACE_ID

    def restore(self, workspace_id: str) -> WorkspaceItem:
        archived_ws = self._archived_dir() / workspace_id
        if not archived_ws.exists():
            raise ValueError(f"归档工作区不存在: {workspace_id}")
        target = self._workspaces_root / workspace_id
        if target.exists():
            raise ValueError(f"工作区已存在: {workspace_id}")
        shutil.move(str(archived_ws), str(target))
        name = workspace_id
        item = WorkspaceItem(id=workspace_id, name=name, created_at=time.time())
        self._config.workspaces.items.append(item)
        logger.info("恢复工作区: %s", workspace_id)
        return item

    def _archived_dir(self) -> Path:
        return self._workspaces_root / ARCHIVED_DIR_NAME

    def ensure_default(self) -> None:
        if self._config.workspaces.get_item(DEFAULT_WORKSPACE_ID) is None:
            self._config.workspaces.items.insert(
                0, WorkspaceItem(id=DEFAULT_WORKSPACE_ID, name="默认工作区")
            )
        ws = self.get_default()
        ws.chroma_dir.mkdir(parents=True, exist_ok=True)
        ws.files_dir.mkdir(parents=True, exist_ok=True)
        ws.sqlite_path.parent.mkdir(parents=True, exist_ok=True)