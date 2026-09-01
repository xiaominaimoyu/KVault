"""混合检索模块，融合 BM25 与向量检索结果。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.bm25_retriever import BM25Retriever
from core.fusion import rrf, weighted_norm
from core.retriever import SearchResult

if TYPE_CHECKING:
    from core.config import Config
    from core.embedding_service import EmbeddingService
    from core.metadata_manager import MetadataManager
    from core.vector_store import VectorStore

logger = logging.getLogger(__name__)


class HybridRetriever:
    """混合检索器，融合 BM25 与向量检索。"""

    def __init__(
        self,
        embedder: "EmbeddingService",
        vector_store: "VectorStore",
        metadata: "MetadataManager",
        config: "Config",
    ):
        self.embedder = embedder
        self.vector_store = vector_store
        self.metadata = metadata
        self.config = config
        self._bm25: BM25Retriever | None = None

    def _ensure_bm25(self) -> BM25Retriever:
        if self._bm25 is None:
            self._bm25 = BM25Retriever(self.metadata)
            self._bm25.build_index()
        return self._bm25

    def search(
        self,
        query: str,
        top_k: int | None = None,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        """混合检索：BM25 + 向量融合，jieba 缺失时降级为纯向量。"""
        if not query or not query.strip():
            return []

        top_k = top_k or self.config.top_k
        hc = self.config.hybrid_search

        if not BM25Retriever.is_jieba_available():
            logger.warning("未安装 jieba，已降级为纯向量检索")
            return self._vector_search(query, top_k, filters)

        bm25 = self._ensure_bm25()
        fetch_k = top_k * 2

        bm25_hits = bm25.search(query, top_k=fetch_k, filters=filters)
        vector_results = self._vector_search(query, top_k=fetch_k, filters=filters)

        bm25_ranking = [h.chunk_id for h in bm25_hits]
        vector_ranking = [r.chunk_id for r in vector_results]

        if hc.strategy == "rrf":
            fused = rrf(
                [bm25_ranking, vector_ranking],
                weights=[hc.bm25_weight, hc.vector_weight],
                k=hc.rrf_k,
            )
        else:
            bm25_scores = [(h.chunk_id, h.score) for h in bm25_hits]
            vector_scores = [(r.chunk_id, r.score) for r in vector_results]
            fused = weighted_norm(
                [bm25_scores, vector_scores],
                weights=[hc.bm25_weight, hc.vector_weight],
            )

        chunk_map: dict[str, SearchResult] = {}
        for r in vector_results:
            chunk_map[r.chunk_id] = r
        for h in bm25_hits:
            if h.chunk_id not in chunk_map:
                chunk_map[h.chunk_id] = SearchResult(
                    chunk_id=h.chunk_id,
                    document_id=h.document_id,
                    document_name=h.document_name,
                    content=h.content,
                    score=h.score,
                    chunk_index=h.chunk_index,
                    metadata={},
                )

        results: list[SearchResult] = []
        for fr in fused[:top_k]:
            base = chunk_map.get(fr.chunk_id)
            if base is None:
                continue
            if base.score < self.config.similarity_threshold:
                continue
            results.append(SearchResult(
                chunk_id=base.chunk_id,
                document_id=base.document_id,
                document_name=base.document_name,
                content=base.content,
                score=fr.score,
                chunk_index=base.chunk_index,
                metadata=base.metadata,
            ))
        return results

    def _vector_search(
        self, query: str, top_k: int, filters: dict | None
    ) -> list[SearchResult]:
        """纯向量检索路径。"""
        query_embedding = self.embedder.embed_query(query.strip())
        raw_results = self.vector_store.search(
            query_embedding=query_embedding, top_k=top_k, filters=filters
        )
        results: list[SearchResult] = []
        for raw in raw_results:
            document_id = raw.metadata.get("document_id", "")
            document_name = raw.metadata.get("file_name", "")
            chunk_index = -1
            parts = raw.chunk_id.rsplit("_", 1)
            if len(parts) == 2:
                try:
                    chunk_index = int(parts[1])

                except ValueError:
                    pass
            if not document_id and len(parts) == 2:
                document_id = parts[0]
            if not document_name and document_id:
                doc = self.metadata.get_document(document_id)
                if doc:
                    document_name = doc.file_name
            results.append(SearchResult(
                chunk_id=raw.chunk_id,
                document_id=document_id,
                document_name=document_name,
                content=raw.content,
                score=raw.score,
                chunk_index=chunk_index,
                metadata=raw.metadata,
            ))
        return results