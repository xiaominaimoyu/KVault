from dataclasses import dataclass

from core.config import Config
from core.embedding_service import EmbeddingService
from core.metadata_manager import MetadataManager
from core.vector_store import VectorStore


@dataclass
class SearchResult:
    chunk_id: str
    document_id: str
    document_name: str
    content: str
    score: float
    chunk_index: int
    metadata: dict


class Retriever:
    def __init__(
        self,
        embedder: EmbeddingService,
        vector_store: VectorStore,
        metadata: MetadataManager,
        config: Config,
    ):
        self.embedder = embedder
        self.vector_store = vector_store
        self.metadata = metadata
        self.config = config

    def search(
        self,
        query: str,
        top_k: int | None = None,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        if not query or not query.strip():
            return []

        top_k = top_k or self.config.top_k
        query_embedding = self.embedder.embed_query(query.strip())
        raw_results = self.vector_store.search(
            query_embedding=query_embedding,
            top_k=top_k,
            filters=filters,
        )

        results: list[SearchResult] = []
        for raw in raw_results:
            if raw.score < self.config.similarity_threshold:
                continue

            document_id = raw.metadata.get("document_id", "")
            document_name = raw.metadata.get("file_name", "")
            chunk_index = self._extract_chunk_index(raw.chunk_id)

            if not document_id:
                parts = raw.chunk_id.rsplit("_", 1)
                if len(parts) == 2:
                    document_id = parts[0]

            if not document_name and document_id:
                doc = self.metadata.get_document(document_id)
                if doc:
                    document_name = doc.file_name

            results.append(
                SearchResult(
                    chunk_id=raw.chunk_id,
                    document_id=document_id,
                    document_name=document_name,
                    content=raw.content,
                    score=raw.score,
                    chunk_index=chunk_index,
                    metadata=raw.metadata,
                )
            )

        return results

    @staticmethod
    def _extract_chunk_index(chunk_id: str) -> int:
        parts = chunk_id.rsplit("_", 1)
        if len(parts) == 2:
            try:
                return int(parts[1])
            except ValueError:
                pass
        return -1
