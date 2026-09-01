import time
from dataclasses import dataclass

import chromadb


@dataclass
class SearchResult:
    chunk_id: str
    content: str
    score: float
    metadata: dict


@dataclass
class ModelVersionInfo:
    """嵌入模型版本信息，用于写入 collection metadata。"""

    model: str
    dimension: int
    created_at: float | None = None


class VectorStore:
    def __init__(
        self,
        persist_dir: str = "./data/chroma_db",
        model_info: ModelVersionInfo | None = None,
    ):
        self.client = chromadb.PersistentClient(path=persist_dir)
        metadata: dict = {"hnsw:space": "cosine"}
        if model_info:
            metadata["embedding_model"] = model_info.model
            metadata["dimension"] = str(model_info.dimension)
            metadata["created_at"] = str(model_info.created_at or time.time())
        self.collection = self.client.get_or_create_collection(
            name="knowledge_base",
            metadata=metadata,
        )

    def set_collection_metadata(
        self, model: str, dimension: int, created_at: float | None = None
    ) -> None:
        """更新 collection 的嵌入模型版本元数据。"""
        self.collection.metadata = {
            "hnsw:space": "cosine",
            "embedding_model": model,
            "dimension": str(dimension),
            "created_at": str(created_at or time.time()),
        }

    def get_collection_metadata(self) -> dict:
        """读取 collection 元数据，返回 embedding_model/dimension/created_at（可能缺失）。"""
        meta = self.collection.metadata or {}
        return {
            "embedding_model": meta.get("embedding_model"),
            "dimension": int(meta["dimension"]) if meta.get("dimension") else None,
            "created_at": float(meta["created_at"]) if meta.get("created_at") else None,
        }

    def add_chunks(self, ids: list[str], texts: list[str],
                   embeddings: list[list[float]], metadatas: list[dict]):
        self.collection.add(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def search(self, query_embedding: list[float], top_k: int = 5,
               filters: dict | None = None) -> list[SearchResult]:
        total = self.collection.count()
        if total == 0:
            return []
        n_results = min(max(top_k, 1), total)
        res = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=filters,
        )
        ids = (res.get("ids") or [[]])[0] or []
        docs = (res.get("documents") or [[]])[0] or []
        dists = (res.get("distances") or [[]])[0] or []
        metas = (res.get("metadatas") or [[]])[0] or []
        results = []
        for cid, doc, dist, meta in zip(ids, docs, dists, metas):
            results.append(SearchResult(
                chunk_id=cid,
                content=doc or "",
                score=1 - dist,
                metadata=meta or {},
            ))
        return results

    def delete_by_document(self, document_id: str):
        self.collection.delete(where={"document_id": document_id})

    def count(self) -> int:
        return self.collection.count()
