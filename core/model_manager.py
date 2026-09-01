"""嵌入模型版本管理与切换工作流。

提供模型一致性校验、备份→重建→校验→可回滚的完整切换工作流。
"""

from __future__ import annotations

import logging
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.config import Config
from core.metadata_manager import MetadataManager
from core.vector_store import ModelVersionInfo, VectorStore

logger = logging.getLogger(__name__)


@dataclass
class SwitchResult:
    """模型切换结果。"""

    success: bool
    backup_path: Path | None
    error: str = ""
    rolled_back: bool = False


class ModelMismatchError(Exception):
    """当前模型与索引模型不一致时抛出。"""


class ModelManager:
    """嵌入模型版本管理与切换编排器。"""

    def __init__(
        self,
        config: Config,
        vector_store: VectorStore,
        metadata: MetadataManager,
    ):
        self.config = config
        self.vector_store = vector_store
        self.metadata = metadata

    def get_indexed_version(self) -> ModelVersionInfo | None:
        """从 collection metadata + SQLite index_meta 读取索引时的模型版本。"""
        cm = self.vector_store.get_collection_metadata()
        model = cm.get("embedding_model")
        if not model:
            model = self.metadata.get_index_meta("embedding_model")
        if not model:
            return None
        dimension = cm.get("dimension")
        if dimension is None:
            dim_str = self.metadata.get_index_meta("dimension")
            dimension = int(dim_str) if dim_str else None
        created_at = cm.get("created_at")
        if created_at is None:
            ts_str = self.metadata.get_index_meta("created_at")
            created_at = float(ts_str) if ts_str else None
        return ModelVersionInfo(model=model, dimension=dimension or 0, created_at=created_at)

    def get_config_version(self) -> ModelVersionInfo:
        """从 config 读取当前配置的模型版本。

        按后端类型取模型标识：ollama 用 embedding_model，
        llama_cpp 用 GGUF 文件名。
        """
        if self.config.embedding_backend == "llama_cpp":
            model_id = Path(self.config.llama_cpp.model_path).name if self.config.llama_cpp.model_path else ""
        else:
            model_id = self.config.embedding_model
        return ModelVersionInfo(
            model=model_id,
            dimension=self.config.last_index_dimension or 0,
            created_at=self.config.last_index_at,
        )

    def check_consistency(self) -> tuple[bool, str]:
        """检查当前模型与索引模型一致性。

        Returns:
            (一致, 消息)。旧索引无模型元数据时返回 (True, "未知版本")，不阻塞。
        """
        indexed = self.get_indexed_version()
        if indexed is None:
            return True, "未知版本（旧索引未记录模型版本，建议切换模型或重建索引）"
        current = self.get_config_version()
        if indexed.model != current.model:
            return False, (
                f"模型不一致：索引使用 '{indexed.model}'，当前配置为 '{current.model}'。"
                f"请通过设置页「切换模型」执行迁移，或参阅 docs/backup-and-migration.md"
            )
        return True, ""

    def _backup(self) -> Path:
        """备份当前 chroma_db + config.json + kb.sqlite 到 data/backups/<timestamp>/。"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_root = self.config.chroma_dir.parent / "backups" / timestamp
        backup_root.mkdir(parents=True, exist_ok=True)

        if self.config.chroma_dir.exists():
            shutil.copytree(self.config.chroma_dir, backup_root / "chroma_db")
        if self.config.sqlite_path.exists():
            shutil.copy2(self.config.sqlite_path, backup_root / "kb.sqlite")
        config_backup = backup_root / "config.json"
        config_backup.write_text(
            __import__("json").dumps(self.config.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("backup created at %s", backup_root)
        return backup_root

    def rollback(self, backup_path: Path) -> None:
        """从备份回滚 chroma_db + kb.sqlite。

        ChromaDB 的 PersistentClient 可能持有 sqlite3 文件句柄，
        删除时遇到 PermissionError 则跳过删除，仅覆盖可写入的文件。
        """
        chroma_backup = backup_path / "chroma_db"
        sqlite_backup = backup_path / "kb.sqlite"

        if chroma_backup.exists() and self.config.chroma_dir.exists():
            try:
                shutil.rmtree(self.config.chroma_dir)
                shutil.copytree(chroma_backup, self.config.chroma_dir)
            except PermissionError:
                logger.warning("chroma_db 目录被占用，跳过目录级回滚，尝试文件级覆盖")
                for src_file in chroma_backup.rglob("*"):
                    if src_file.is_file():
                        rel = src_file.relative_to(chroma_backup)
                        dst_file = self.config.chroma_dir / rel
                        dst_file.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            shutil.copy2(src_file, dst_file)
                        except PermissionError:
                            logger.warning("跳过被占用文件: %s", dst_file)
        if sqlite_backup.exists():
            try:
                shutil.copy2(sqlite_backup, self.config.sqlite_path)
            except PermissionError:
                logger.warning("kb.sqlite 被占用，跳过回滚")
        logger.info("rolled back from %s", backup_path)

    def switch_model(
        self,
        new_model: str,
        rebuild_fn: Callable[[], None],
        progress_cb: Callable[[str], None] | None = None,
    ) -> SwitchResult:
        """执行备份→重建→校验→可回滚四步工作流。

        Args:
            new_model: 新模型名。
            rebuild_fn: 重建索引的回调（无参数，失败时抛异常）。
            progress_cb: 进度回调（接收阶段描述字符串）。
        """
        def notify(msg: str) -> None:
            logger.info(msg)
            if progress_cb:
                progress_cb(msg)

        try:
            notify("步骤 1/4: 备份当前索引")
            backup_path = self._backup()

            notify("步骤 2/4: 更新模型配置并重建索引")
            old_model = self.config.embedding_model
            self.config.embedding_model = new_model
            rebuild_fn()

            notify("步骤 3/4: 校验新索引一致性")
            indexed = self.get_indexed_version()
            if indexed and indexed.model != new_model:
                notify("校验失败：新索引模型与预期不符，执行回滚")
                self.config.embedding_model = old_model
                self.rollback(backup_path)
                return SwitchResult(
                    success=False,
                    backup_path=backup_path,
                    error=f"校验失败：索引模型 '{indexed.model}' != '{new_model}'",
                    rolled_back=True,
                )

            notify("步骤 4/4: 持久化配置")
            self.config.last_index_model = new_model
            self.config.last_index_at = time.time()
            self.config.save()
            self.metadata.set_index_meta("embedding_model", new_model)
            if indexed:
                self.metadata.set_index_meta("dimension", str(indexed.dimension))

            return SwitchResult(success=True, backup_path=backup_path)

        except Exception as e:
            logger.exception("模型切换失败")
            old = locals().get("old_model")
            if old is not None:
                self.config.embedding_model = old
            backup = locals().get("backup_path")
            if backup:
                notify("异常发生，执行回滚")
                self.rollback(backup)
                return SwitchResult(success=False, backup_path=backup, error=str(e), rolled_back=True)
            return SwitchResult(success=False, backup_path=None, error=str(e))

    def switch_backend(
        self,
        new_backend: str,
        new_model_id: str,
        rebuild_fn: Callable[[], None],
        progress_cb: Callable[[str], None] | None = None,
    ) -> SwitchResult:
        """执行后端切换的备份→重建→校验→可回滚四步工作流。

        复用 switch_model 的工作流，额外更新 config.embedding_backend
        与对应模型标识字段（ollama 更新 embedding_model，llama_cpp 更新 llama_cpp.model_path）。

        Args:
            new_backend: 新后端类型（"ollama" 或 "llama_cpp"）。
            new_model_id: 新模型标识。ollama 为模型名，llama_cpp 为 GGUF 文件路径。
            rebuild_fn: 重建索引的回调（无参数，失败时抛异常）。
            progress_cb: 进度回调（接收阶段描述字符串）。
        """
        def notify(msg: str) -> None:
            logger.info(msg)
            if progress_cb:
                progress_cb(msg)

        if new_backend == "llama_cpp":
            expected_model_id = Path(new_model_id).name if new_model_id else ""
        else:
            expected_model_id = new_model_id

        old_backend = self.config.embedding_backend
        old_embedding_model = self.config.embedding_model
        old_llama_cpp_model_path = self.config.llama_cpp.model_path

        try:
            notify("步骤 1/4: 备份当前索引")
            backup_path = self._backup()

            notify("步骤 2/4: 更新后端配置并重建索引")
            self.config.embedding_backend = new_backend
            if new_backend == "llama_cpp":
                self.config.llama_cpp.model_path = new_model_id
            else:
                self.config.embedding_model = new_model_id
            rebuild_fn()

            notify("步骤 3/4: 校验新索引一致性")
            indexed = self.get_indexed_version()
            if indexed and indexed.model != expected_model_id:
                notify("校验失败：新索引模型与预期不符，执行回滚")
                self.config.embedding_backend = old_backend
                self.config.embedding_model = old_embedding_model
                self.config.llama_cpp.model_path = old_llama_cpp_model_path
                self.rollback(backup_path)
                return SwitchResult(
                    success=False,
                    backup_path=backup_path,
                    error=f"校验失败：索引模型 '{indexed.model}' != '{expected_model_id}'",
                    rolled_back=True,
                )

            notify("步骤 4/4: 持久化配置")
            self.config.last_index_model = expected_model_id
            self.config.last_index_at = time.time()
            self.config.save()
            self.metadata.set_index_meta("embedding_model", expected_model_id)
            if indexed:
                self.metadata.set_index_meta("dimension", str(indexed.dimension))

            return SwitchResult(success=True, backup_path=backup_path)

        except Exception as e:
            logger.exception("后端切换失败")
            self.config.embedding_backend = old_backend
            self.config.embedding_model = old_embedding_model
            self.config.llama_cpp.model_path = old_llama_cpp_model_path
            backup = locals().get("backup_path")
            if backup:
                notify("异常发生，执行回滚")
                self.rollback(backup)
                return SwitchResult(success=False, backup_path=backup, error=str(e), rolled_back=True)
            return SwitchResult(success=False, backup_path=None, error=str(e))
