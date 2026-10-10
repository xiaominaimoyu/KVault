"""索引增量更新模块。

基于文件指纹识别新增/修改/删除文档，仅重索引受影响文档。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from core.config import Config
from core.document_parser import DocumentParser
from core.embedding_service import EmbeddingService
from core.fingerprint import Fingerprint, FingerprintError
from core.metadata_manager import MetadataManager
from core.text_splitter import KnowledgeTextSplitter
from core.vector_store import VectorStore

logger = logging.getLogger(__name__)


@dataclass
class DiffReport:
    """数据目录与 SQLite 指纹的差异清单。"""

    added: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)


@dataclass
class UpdateResult:
    """增量更新结果。"""

    success_count: int = 0
    fail_count: int = 0
    dirty_doc_ids: list[str] = field(default_factory=list)


class IncrementalUpdater:
    """增量更新编排器。"""

    def __init__(
        self,
        config: Config,
        parser: DocumentParser,
        splitter: KnowledgeTextSplitter,
        embedder: EmbeddingService,
        vector_store: VectorStore,
        metadata: MetadataManager,
    ):
        self.config = config
        self.parser = parser
        self.splitter = splitter
        self.embedder = embedder
        self.vector_store = vector_store
        self.metadata = metadata

    def scan_diffs(self) -> DiffReport:
        """扫描 config.files_dir 比对 SQLite 指纹，生成差异清单。"""
        report = DiffReport()
        fingerprints = self.metadata.list_all_fingerprints()

        stored_to_doc_id: dict[str, str] = {}
        for doc_id, fp in fingerprints.items():
            stored_to_doc_id[fp["stored_path"]] = doc_id

        files_dir = self.config.files_dir
        seen_paths: set[str] = set()

        if files_dir.exists():
            # 必须递归遍历：导入时保留了源文件的目录层级
            # （files_dir/<来源目录>/<文件名>），非递归扫描会把它们全部误判为新增，
            # 同时把原有记录误判为已删除。
            for p in sorted(files_dir.rglob("*")):
                if not p.is_file():
                    continue
                stored = str(p)
                seen_paths.add(stored)
                try:
                    current_fp = Fingerprint.compute(stored)
                except FingerprintError:
                    report.unreadable.append(stored)
                    continue

                doc_id = stored_to_doc_id.get(stored)
                if doc_id is None:
                    report.added.append(stored)
                else:
                    old_fp = fingerprints[doc_id]
                    if (
                        old_fp.get("content_hash") != current_fp.content_hash
                        or old_fp.get("mtime") != current_fp.mtime
                    ):
                        report.modified.append(stored)

        for stored_path, doc_id in stored_to_doc_id.items():
            if stored_path not in seen_paths:
                report.deleted.append(stored_path)

        return report

    def update(
        self,
        report: DiffReport,
        progress_cb: Callable[[str, str], None] | None = None,
    ) -> UpdateResult:
        """处理新增/修改/删除三类文档。

        Args:
            report: scan_diffs 返回的差异清单。
            progress_cb: 进度回调 (stored_path, status)。
        """
        from core.ingest import ingest_document

        result = UpdateResult()

        for stored in report.deleted:
            try:
                doc_map = self.metadata.list_all_fingerprints()
                for doc_id, fp in doc_map.items():
                    if fp["stored_path"] == stored:
                        self.metadata.delete_document(doc_id)
                        break
                if progress_cb:
                    progress_cb(stored, "deleted")
            except Exception as e:
                logger.warning("删除失败 %s: %s", stored, e)
                result.fail_count += 1

        for stored in report.added + report.modified:
            try:
                ingest_document(
                    file_path=stored,
                    config=self.config,
                    parser=self.parser,
                    splitter=self.splitter,
                    embedder=self.embedder,
                    vector_store=self.vector_store,
                    metadata=self.metadata,
                )
                result.success_count += 1
                if progress_cb:
                    progress_cb(stored, "indexed")
            except Exception as e:
                logger.warning("索引失败 %s: %s", stored, e)
                result.fail_count += 1
                result.dirty_doc_ids.append(stored)
                if progress_cb:
                    progress_cb(stored, f"failed: {e}")

        return result

    def rebuild_all(
        self, progress_cb: Callable[[str, str], None] | None = None
    ) -> UpdateResult:
        """全量重建：删除所有文档后重新索引 files_dir 中的全部文件。"""
        from core.ingest import ingest_document

        result = UpdateResult()
        for doc in self.metadata.list_documents():
            self.metadata.delete_document(doc.id)

        files_dir = self.config.files_dir
        if not files_dir.exists():
            return result

        for p in files_dir.iterdir():
            if p.is_dir():
                continue
            try:
                ingest_document(
                    file_path=str(p),
                    config=self.config,
                    parser=self.parser,
                    splitter=self.splitter,
                    embedder=self.embedder,
                    vector_store=self.vector_store,
                    metadata=self.metadata,
                )
                result.success_count += 1
                if progress_cb:
                    progress_cb(str(p), "indexed")
            except Exception as e:
                logger.warning("重建失败 %s: %s", p, e)
                result.fail_count += 1
                result.dirty_doc_ids.append(str(p))
                if progress_cb:
                    progress_cb(str(p), f"failed: {e}")

        return result
