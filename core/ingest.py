import shutil
from pathlib import Path

from core.config import Config
from core.document_parser import DocumentParser
from core.embedding_service import EmbeddingService
from core.fingerprint import Fingerprint, FingerprintError
from core.metadata_manager import DEFAULT_PARTITION_ID, MetadataManager
from core.text_splitter import KnowledgeTextSplitter
from core.vector_store import VectorStore

#: SQLite 中 content_preview 的最大长度。
#:
#: 早期版本固定截断到 200 字，导致 BM25 只能索引每个块的开头——长块的后半部分
#: 永远无法被关键词命中。这里放宽到足以覆盖整块，同时仍为数据库体积设上限。
CONTENT_PREVIEW_LIMIT = 4000


def resolve_stored_path(config: Config, src: Path) -> Path:
    """为导入的文件计算存储路径，保留来源目录以区分同名文件。

    旧实现直接用 ``files_dir / 文件名`` 平铺存储，导致不同目录下的同名文件
    （例如 ``a/报告.md`` 与 ``b/报告.md``）映射到同一路径，并互相覆盖、删除
    对方的向量记录——这是一处静默的数据丢失。

    新实现把源文件所在目录名作为一级子目录（``files_dir/<父目录>/<文件名>``），
    足以区分常见的同名冲突，同时避免把整棵目录树搬进知识库。剩余冲突由
    :func:`ingest_document` 追加数字后缀处理。

    例外：源文件本身已经位于 ``files_dir`` 内（由本库管理、或增量更新流程直接
    处理），此时原地存储，避免再套一层目录产生重复副本。
    """
    try:
        inside = src.resolve().is_relative_to(config.files_dir.resolve())
    except (OSError, ValueError):
        inside = False
    if inside:
        return src

    parent = src.parent.name
    base = config.files_dir / parent if parent else config.files_dir
    return base / src.name


def _safe_resolve(path: Path) -> Path | None:
    """尽力解析真实路径，失败时返回 ``None``。"""
    try:
        return path.resolve()
    except OSError:
        return None


def _next_free_path(stored: Path, metadata: MetadataManager) -> Path:
    """为撞车的存储路径寻找未占用的替代位置。"""
    candidate = stored
    for index in range(1, 10_000):
        candidate = stored.with_name(f"{stored.stem} ({index}){stored.suffix}")
        if not candidate.exists() and not metadata.get_document_by_stored_path(str(candidate)):
            return candidate
    raise ValueError(f"无法为 {stored.name} 分配唯一存储路径")


def _preview_of(content: str) -> str:
    """生成入库的块文本摘要。

    **必须覆盖整块内容**：BM25 检索直接使用 ``content_preview`` 建索引，
    若在这里截断，长块的后半部分将永远无法被关键词命中。
    仅在超长时截断以控制数据库体积。
    """
    flat = content.replace("\n", " ").strip()
    if len(flat) <= CONTENT_PREVIEW_LIMIT:
        return flat
    return flat[:CONTENT_PREVIEW_LIMIT]


def ingest_document(
    file_path: str,
    config: Config,
    parser: DocumentParser,
    splitter: KnowledgeTextSplitter,
    embedder: EmbeddingService,
    vector_store: VectorStore,
    metadata: MetadataManager,
    partition_id: str = DEFAULT_PARTITION_ID,
) -> str:
    src = Path(file_path)
    stored = resolve_stored_path(config, src)

    # 仅当确实是同一条记录（同源文件）被重新导入时才删除重建；
    # 否则说明路径撞车，必须换名字而不是覆盖。
    existing = metadata.get_document_by_stored_path(str(stored))
    if existing and Path(existing.original_path or "").resolve() == _safe_resolve(src):
        metadata.delete_document(existing.id)
        existing = None

    if existing is not None:
        stored = _next_free_path(stored, metadata)

    # 存储路径现在带来源目录层级，复制前必须确保目录存在
    stored.parent.mkdir(parents=True, exist_ok=True)

    doc_id = metadata.create_document(
        file_name=src.name,
        original_path=str(src),
        stored_path=str(stored),
        file_ext=src.suffix.lower(),
        file_size=src.stat().st_size,
        partition_id=partition_id,
    )

    try:
        if src.resolve() != stored.resolve():
            shutil.copy2(src, stored)
        metadata.update_status(doc_id, "indexing")

        parsed = parser.parse(str(stored))
        if not parsed.content or not parsed.content.strip():
            raise ValueError("Document content is empty")

        chunks = splitter.split(
            parsed.content,
            {
                "document_id": doc_id,
                "file_name": src.name,
                "file_ext": src.suffix.lower(),
                "partition_id": partition_id,
            },
        )
        if not chunks:
            raise ValueError("No valid chunks after splitting")

        embeddings = embedder.embed_texts([c.content for c in chunks])

        ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
        vector_store.add_chunks(
            ids=ids,
            texts=[c.content for c in chunks],
            embeddings=embeddings,
            metadatas=[c.metadata for c in chunks],
        )

        chunk_meta = [
            (i, _preview_of(c.content), ids[i]) for i, c in enumerate(chunks)
        ]
        metadata.add_chunks(doc_id, chunk_meta)
        metadata.update_status(doc_id, "indexed", chunk_count=len(chunks))

        try:
            fp = Fingerprint.compute(stored)
            metadata.update_fingerprint(doc_id, fp.content_hash, fp.mtime)
        except FingerprintError:
            pass

        return doc_id
    except Exception as e:
        metadata.update_status(doc_id, "failed", error_message=str(e))
        raise
