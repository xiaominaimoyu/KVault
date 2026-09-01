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
            for p in files_dir.iterdir():
                if p.is_dir():
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