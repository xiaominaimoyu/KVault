import logging
import os
from pathlib import Path
from typing import Optional

from core.config import Config
from core.embedding_service import EmbeddingService
from core.metadata_manager import MetadataManager
from core.retriever import Retriever
from core.vector_store import VectorStore

logger = logging.getLogger(__name__)

_MAX_CONTENT_LEN = 800
_MAX_PREVIEW_LEN = 2000
_services_cache = None


def _load_config() -> Config:
    cfg = Config.load("config.json")
    chroma_path = os.getenv("CHROMA_PATH")
    db_path = os.getenv("DB_PATH")
    if chroma_path:
        cfg.chroma_dir = Path(chroma_path)
    if db_path:
        cfg.sqlite_path = Path(db_path)
    return cfg


def _get_services():
    global _services_cache
    if _services_cache is not None:
        return _services_cache
    config = _load_config()
    vector_store = VectorStore(str(config.chroma_dir))
    metadata = MetadataManager(str(config.sqlite_path), vector_store=vector_store)
    embedder = EmbeddingService(
        model=config.embedding_model,
        base_url=config.ollama_base_url,
        batch_size=config.embedding_batch_size,
    )
    retriever = Retriever(
        embedder=embedder,
        vector_store=vector_store,
        metadata=metadata,
        config=config,
    )
    _services_cache = (config, retriever, metadata)
    return _services_cache


def reset_services_cache():
    global _services_cache
    _services_cache = None


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "..."


def search_knowledge_base(
    query: str,
    top_k: int = 5,
    partition_filter: Optional[str] = None,
    tag_filters: Optional[list[str]] = None,
) -> dict:
    if not query or not query.strip():
        return {"error": "query cannot be empty"}

    top_k = max(1, min(int(top_k), 50))

    try:
        config, retriever, metadata = _get_services()
    except Exception as e:
        logger.exception("Failed to init search services")
        return {"error": f"service init failed: {e}"}

    chroma_filters = None
    target_partition_id: Optional[str] = None
    target_tag_names: set[str] = set()

    if partition_filter and partition_filter.strip():
        partition_filter = partition_filter.strip()
        for p in metadata.list_partitions():
            if p["name"] == partition_filter:
                target_partition_id = p["id"]
                break
        if target_partition_id is None:
            return {"results": []}

    if tag_filters:
        target_tag_names = {str(t).strip() for t in tag_filters if str(t).strip()}

    if target_partition_id is not None or target_tag_names:
        docs = metadata.list_documents(
            partition_id=target_partition_id,
            tag_ids=None,
        )
        if target_tag_names:
            tag_map = metadata.get_documents_tag_map([d.id for d in docs])
            docs = [
                d for d in docs
                if target_tag_names.intersection(
                    {t["name"] for t in tag_map.get(d.id, [])}
                )
            ]
        doc_ids = [d.id for d in docs]
        if not doc_ids:
            return {"results": []}
        chroma_filters = {"document_id": {"$in": doc_ids}}

    try:
        results = retriever.search(
            query.strip(), top_k=top_k, filters=chroma_filters
        )
    except Exception as e:
        logger.exception("Semantic search failed")
        return {"error": f"search failed: {e}"}

    return {
        "results": [
            {
                "document_id": r.document_id,
                "document_name": r.document_name,
                "chunk_id": r.chunk_id,
                "chunk_index": r.chunk_index,
                "score": round(float(r.score), 4),
                "content": _truncate(r.content, _MAX_CONTENT_LEN),
            }
            for r in results
        ]
    }


def list_knowledge_bases() -> dict:
    try:
        _, _, metadata = _get_services()
    except Exception as e:
        logger.exception("Failed to init metadata")
        return {"error": f"service init failed: {e}"}

    try:
        partitions = metadata.list_partitions_with_counts()
    except Exception as e:
        logger.exception("Failed to list partitions")
        return {"error": f"list partitions failed: {e}"}

    return {
        "partitions": [
            {
                "id": p["id"],
                "name": p["name"],
                "document_count": p["doc_count"],
            }
            for p in partitions
        ]
    }


def get_document_preview(document_id: str) -> dict:
    if not document_id or not document_id.strip():
        return {"error": "document_id cannot be empty"}

    document_id = document_id.strip()

    try:
        _, _, metadata = _get_services()
    except Exception as e:
        logger.exception("Failed to init metadata")
        return {"error": f"service init failed: {e}"}

    doc = metadata.get_document(document_id)
    if not doc:
        candidates = [
            d for d in metadata.list_documents()
            if document_id.lower() in d.file_name.lower()
        ]
        if len(candidates) == 1:
            doc = candidates[0]
        elif len(candidates) > 1:
            return {
                "error": "multiple matches; use exact document_id",
                "matches": [{"id": d.id, "name": d.file_name} for d in candidates[:10]],
            }

    if not doc:
        return {"error": "document not found"}

    chunks = metadata.get_document_chunks(doc.id)
    preview = "\n\n".join(c["content_preview"] for c in chunks)
    if not preview:
        preview = "(no preview)"

    tags = [t["name"] for t in metadata.get_document_tags(doc.id)]

    return {
        "document": {
            "id": doc.id,
            "name": doc.file_name,
            "file_ext": doc.file_ext,
            "partition": doc.partition_name or "uncategorized",
            "status": doc.status,
            "chunk_count": doc.chunk_count,
            "tags": tags,
            "preview": _truncate(preview, _MAX_PREVIEW_LEN),
        }
    }
