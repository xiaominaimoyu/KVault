
from core.text_splitter import KnowledgeTextSplitter


def test_split_empty():
    splitter = KnowledgeTextSplitter(chunk_size=50, chunk_overlap=10)
    assert splitter.split("", {"document_id": "x"}) == []


def test_split_produces_chunks_with_metadata():
    splitter = KnowledgeTextSplitter(chunk_size=40, chunk_overlap=5)
    content = "A" * 100
    chunks = splitter.split(content, {"document_id": "doc1", "file_name": "a.txt"})
    assert len(chunks) >= 2
    assert chunks[0].metadata["document_id"] == "doc1"
    assert chunks[0].metadata["chunk_index"] == 0
    assert chunks[-1].metadata["total_chunks"] == len(chunks)
