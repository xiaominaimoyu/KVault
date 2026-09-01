"""BM25 检索模块，使用 jieba 中文分词构建内存倒排索引。

jieba 为可选依赖，缺失时 is_jieba_available() 返回 False。
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.metadata_manager import MetadataManager

logger = logging.getLogger(__name__)


@dataclass
class BM25Hit:
    """BM25 检索单条结果。"""

    chunk_id: str
    document_id: str
    document_name: str
    content: str
    score: float
    chunk_index: int


class BM25Retriever:
    """基于 jieba 分词的 BM25 检索器。"""

    def __init__(self, metadata: "MetadataManager", k1: float = 1.5, b: float = 0.75):
        self.metadata = metadata
        self.k1 = k1
        self.b = b
        self._docs: list[dict] = []
        self._doc_tokens: list[list[str]] = []
        self._doc_len: list[int] = []
        self._avg_len: float = 0.0
        self._df: dict[str, int] = {}
        self._idf: dict[str, float] = {}
        self._tf: list[dict[str, int]] = []
        self._N: int = 0

    @staticmethod
    def is_jieba_available() -> bool:
        try:
            import jieba  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        try:
            import jieba
            return [t for t in jieba.cut(text) if t.strip()]
        except ImportError:
            return [t for t in text.split() if t.strip()]

    def build_index(self) -> None:
        """从 SQLite chunks 加载所有片段，构建 BM25 倒排索引。"""
        self._docs = []
        self._doc_tokens = []
        self._doc_len = []
        self._df = {}
        self._tf = []

        for doc in self.metadata.list_documents():
            chunks = self.metadata.get_document_chunks(doc.id)
            for chunk in chunks:
                chunk_id = chunk.get("chroma_id") or chunk.get("id", "")
                content = chunk.get("content_preview", "")
                tokens = self._tokenize(content)
                tf: dict[str, int] = {}
                for t in tokens:
                    tf[t] = tf.get(t, 0) + 1
                self._docs.append({
                    "chunk_id": chunk_id,
                    "document_id": doc.id,
                    "document_name": doc.file_name,
                    "content": content,
                    "chunk_index": chunk.get("chunk_index", -1),
                })
                self._doc_tokens.append(tokens)
                self._doc_len.append(len(tokens))
                self._tf.append(tf)
                for term in tf:
                    self._df[term] = self._df.get(term, 0) + 1

        self._N = len(self._docs)
        self._avg_len = sum(self._doc_len) / self._N if self._N > 0 else 0.0
        self._idf = {}
        for term, df in self._df.items():
            self._idf[term] = math.log((self._N - df + 0.5) / (df + 0.5) + 1.0)
        logger.info("BM25 index built: %d docs, avg_len=%.1f", self._N, self._avg_len)

    def search(
        self,
        query: str,
        top_k: int = 5,
        filters: dict | None = None,
    ) -> list[BM25Hit]:
        """BM25 检索，返回 top_k 结果。"""
        if self._N == 0 or not query.strip():
            return []

        allowed_doc_ids: set[str] | None = None
        if filters and "document_id" in filters:
            cond = filters["document_id"]
            if isinstance(cond, dict) and "$in" in cond:
                allowed_doc_ids = set(cond["$in"])
            elif isinstance(cond, str):
                allowed_doc_ids = {cond}

        query_tokens = self._tokenize(query)
        scores: list[tuple[int, float]] = []
        for i in range(self._N):
            if allowed_doc_ids is not None:
                if self._docs[i]["document_id"] not in allowed_doc_ids:
                    continue
            score = 0.0
            doc_len = self._doc_len[i]
            for qt in query_tokens:
                if qt not in self._idf:
                    continue
                tf = self._tf[i].get(qt, 0)
                if tf == 0:
                    continue
                idf = self._idf[qt]
                score += idf * (tf * (self.k1 + 1)) / (
                    tf + self.k1 * (1 - self.b + self.b * doc_len / (self._avg_len or 1))
                )
            if score > 0:
                scores.append((i, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        results: list[BM25Hit] = []
        for idx, score in scores[:top_k]:
            d = self._docs[idx]
            results.append(BM25Hit(
                chunk_id=d["chunk_id"],
                document_id=d["document_id"],
                document_name=d["document_name"],
                content=d["content"],
                score=score,
                chunk_index=d["chunk_index"],
            ))
        return results