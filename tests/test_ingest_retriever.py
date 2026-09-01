
from core.ingest import ingest_document
from core.retriever import Retriever


def test_ingest_and_search(
    tmp_config, parser, splitter, fake_embedder, vector_store, metadata, sample_txt
):
    doc_id = ingest_document(
        str(sample_txt),
        tmp_config,
        parser,
        splitter,
        fake_embedder,
        vector_store,
        metadata,
    )
    doc = metadata.get_document(doc_id)
    assert doc is not None
    assert doc.status == "indexed"
    assert doc.chunk_count > 0
    assert vector_store.count() == doc.chunk_count

    tmp_config.similarity_threshold = -1.0
    retriever = Retriever(fake_embedder, vector_store, metadata, tmp_config)
    results = retriever.search("Deep learning uses neural networks", top_k=3)
    assert len(results) >= 1
    assert results[0].document_id == doc_id


def test_ingest_same_path_reindex(
    tmp_config, parser, splitter, fake_embedder, vector_store, metadata, sample_txt
):
    # First ingest copies into files_dir
    doc_id = ingest_document(
        str(sample_txt), tmp_config, parser, splitter, fake_embedder, vector_store, metadata
    )
    doc = metadata.get_document(doc_id)
    stored = doc.stored_path
    metadata.delete_document(doc_id, delete_file=False)
    # Re-ingest from stored path (same src and dest)
    new_id = ingest_document(
        stored, tmp_config, parser, splitter, fake_embedder, vector_store, metadata
    )
    assert metadata.get_document(new_id).status == "indexed"


def test_ingest_with_partition(
    tmp_config, parser, splitter, fake_embedder, vector_store, metadata, sample_txt
):
    pid = metadata.create_partition("Research")
    doc_id = ingest_document(
        str(sample_txt),
        tmp_config,
        parser,
        splitter,
        fake_embedder,
        vector_store,
        metadata,
        partition_id=pid,
    )
    assert metadata.get_document(doc_id).partition_id == pid
