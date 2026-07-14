
from core.vector_store import VectorStore


def test_empty_search_returns_empty(vector_store: VectorStore, fake_embedder):
    emb = fake_embedder.embed_query("hello")
    results = vector_store.search(emb, top_k=5)
    assert results == []


def test_add_search_delete(vector_store: VectorStore, fake_embedder):
    texts = ["machine learning basics", "cooking recipes"]
    embeddings = fake_embedder.embed_texts(texts)
    ids = ["docA_0", "docB_0"]
    metas = [
        {"document_id": "docA", "file_name": "a.txt"},
        {"document_id": "docB", "file_name": "b.txt"},
    ]
    vector_store.add_chunks(ids, texts, embeddings, metas)
    assert vector_store.count() == 2

    hits = vector_store.search(fake_embedder.embed_query("machine learning"), top_k=2)
    assert len(hits) >= 1
    assert hits[0].chunk_id in ids

    vector_store.delete_by_document("docA")
    assert vector_store.count() == 1
