
import mcp_server.tools as tools


def test_search_empty_query(monkeypatch, tmp_config, metadata, vector_store, fake_embedder):
    tools.reset_services_cache()
    from core.retriever import Retriever

    retriever = Retriever(fake_embedder, vector_store, metadata, tmp_config)
    monkeypatch.setattr(tools, "_get_services", lambda: (tmp_config, retriever, metadata))
    assert tools.search_knowledge_base("")["error"]


def test_list_and_preview(
    monkeypatch, tmp_config, metadata, vector_store, fake_embedder, parser, splitter, sample_txt
):
    tools.reset_services_cache()
    from core.ingest import ingest_document
    from core.retriever import Retriever

    doc_id = ingest_document(
        str(sample_txt), tmp_config, parser, splitter, fake_embedder, vector_store, metadata
    )
    retriever = Retriever(fake_embedder, vector_store, metadata, tmp_config)
    monkeypatch.setattr(tools, "_get_services", lambda: (tmp_config, retriever, metadata))

    listed = tools.list_knowledge_bases()
    assert "partitions" in listed
    assert len(listed["partitions"]) >= 1

    preview = tools.get_document_preview(doc_id)
    assert preview["document"]["id"] == doc_id

    results = tools.search_knowledge_base("neural", top_k=3)
    assert "results" in results


def test_partition_filter_empty(monkeypatch, tmp_config, metadata, vector_store, fake_embedder):
    tools.reset_services_cache()
    from core.retriever import Retriever

    retriever = Retriever(fake_embedder, vector_store, metadata, tmp_config)
    monkeypatch.setattr(tools, "_get_services", lambda: (tmp_config, retriever, metadata))
    out = tools.search_knowledge_base("anything", partition_filter="NoSuchPartition")
    assert out == {"results": []}
