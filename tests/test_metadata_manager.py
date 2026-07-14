
import pytest
from core.metadata_manager import DEFAULT_PARTITION_ID, MetadataManager


def test_create_and_list_documents(metadata: MetadataManager, tmp_path):
    doc_id = metadata.create_document(
        file_name="a.txt",
        stored_path=str(tmp_path / "a.txt"),
        file_ext=".txt",
        file_size=10,
    )
    docs = metadata.list_documents()
    assert any(d.id == doc_id for d in docs)


def test_delete_partition_defaults_to_default_id(metadata: MetadataManager, tmp_path):
    pid = metadata.create_partition("TempPart")
    doc_id = metadata.create_document(
        file_name="b.txt",
        stored_path=str(tmp_path / "b.txt"),
        file_ext=".txt",
        file_size=1,
        partition_id=pid,
    )
    metadata.delete_partition(pid)
    doc = metadata.get_document(doc_id)
    assert doc is not None
    assert doc.partition_id == DEFAULT_PARTITION_ID


def test_cannot_delete_default_partition(metadata: MetadataManager):
    with pytest.raises(ValueError):
        metadata.delete_partition(DEFAULT_PARTITION_ID)


def test_duplicate_partition_name(metadata: MetadataManager):
    metadata.create_partition("UniqueNameX")
    with pytest.raises(ValueError):
        metadata.create_partition("UniqueNameX")


def test_tags_and_batch_map(metadata: MetadataManager, tmp_path):
    doc_id = metadata.create_document(
        file_name="c.txt",
        stored_path=str(tmp_path / "c.txt"),
        file_ext=".txt",
        file_size=1,
    )
    tag_id = metadata.create_tag("alpha")
    metadata.set_document_tags(doc_id, [tag_id])
    tag_map = metadata.get_documents_tag_map([doc_id])
    assert tag_map[doc_id][0]["name"] == "alpha"


def test_add_chunks_executemany(metadata: MetadataManager, tmp_path):
    doc_id = metadata.create_document(
        file_name="d.txt",
        stored_path=str(tmp_path / "d.txt"),
        file_ext=".txt",
        file_size=1,
    )
    metadata.add_chunks(doc_id, [(0, "preview0", f"{doc_id}_0"), (1, "preview1", f"{doc_id}_1")])
    chunks = metadata.get_document_chunks(doc_id)
    assert len(chunks) == 2
