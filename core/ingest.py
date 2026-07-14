import shutil
from pathlib import Path

from core.config import Config
from core.document_parser import DocumentParser
from core.embedding_service import EmbeddingService
from core.metadata_manager import DEFAULT_PARTITION_ID, MetadataManager
from core.text_splitter import KnowledgeTextSplitter
from core.vector_store import VectorStore


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
    stored = config.files_dir / src.name

    existing = metadata.get_document_by_stored_path(str(stored))
    if existing:
        metadata.delete_document(existing.id)

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
            (i, c.content[:200].replace("\n", " "), ids[i])
            for i, c in enumerate(chunks)
        ]
        metadata.add_chunks(doc_id, chunk_meta)
        metadata.update_status(doc_id, "indexed", chunk_count=len(chunks))
        return doc_id
    except Exception as e:
        metadata.update_status(doc_id, "failed", error_message=str(e))
        raise
