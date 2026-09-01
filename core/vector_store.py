import chromadb
from dataclasses import dataclass


@dataclass
class SearchResult:
    chunk_id: str
    content: str
    score: float
    metadata: dict


class VectorStore:
    def __init__(self, persist_dir: str = "./data/chroma_db"):
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(
            name="knowledge_base",
            metadata={"hnsw:space": "cosine"},
        )

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
