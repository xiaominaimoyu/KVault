from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.evaluator import (
    EvalSample,
    EvalSet,
    EvalSetFormatError,
    RetrievalEvaluator,
    load_eval_set,
)
from core.retriever import Retriever
from tests.conftest import FakeEmbedder


def _seed_one_doc(
    tmp_config, fake_embedder, vector_store, metadata, file_name="alpha.txt"
):
    text = "alpha beta gamma delta epsilon"
    embedding = fake_embedder.embed_query(text)
    doc_id = metadata.create_document(
        file_name=file_name,
        original_path=file_name,
        stored_path=str(tmp_config.files_dir / file_name),
        file_ext=".txt",
        file_size=len(text),
    )
    chunk_id = f"{doc_id}_0"
    vector_store.add_chunks(
        ids=[chunk_id],
        texts=[text],
        embeddings=[embedding],
        metadatas=[{"document_id": doc_id, "file_name": file_name, "partition_id": ""}],
    )
    metadata.add_chunks(
        doc_id=doc_id,
        chunks=[(0, text[:200], chunk_id)],
    )
    metadata.update_status(doc_id, status="indexed", chunk_count=1)
    return doc_id, text


def test_eval_recall_mrr(tmp_config, fake_embedder, vector_store, metadata):
    doc_id, text = _seed_one_doc(tmp_config, fake_embedder, vector_store, metadata)

    retriever = Retriever(fake_embedder, vector_store, metadata, tmp_config)
    eval_set = EvalSet(
        name="t",
        description="",
        samples=[EvalSample(query=text, expected_doc_ids=[doc_id])],
    )
    evaluator = RetrievalEvaluator(retriever=retriever, metadata=metadata)
    report = evaluator.run(eval_set, top_k=10)

    assert report.total_samples == 1
    assert report.hit_samples == 1
    assert report.avg_mrr == pytest.approx(1.0)
    for k, v in report.avg_recall_at_k.items():
        assert v == pytest.approx(1.0), f"Recall@{k} should be 1.0, got {v}"


def test_eval_read_only(tmp_config, fake_embedder, vector_store, metadata):
    doc_id, text = _seed_one_doc(tmp_config, fake_embedder, vector_store, metadata)

    before_vectors = vector_store.count()
    before_docs = len(metadata.list_documents())

    retriever = Retriever(fake_embedder, vector_store, metadata, tmp_config)
    eval_set = EvalSet(
        name="t",
        description="",
        samples=[EvalSample(query=text, expected_doc_ids=[doc_id])],
    )
    evaluator = RetrievalEvaluator(retriever=retriever, metadata=metadata)
    evaluator.run(eval_set, top_k=10)

    assert vector_store.count() == before_vectors
    assert len(metadata.list_documents()) == before_docs


def test_eval_miss_query(tmp_config, fake_embedder, vector_store, metadata):
    _seed_one_doc(tmp_config, fake_embedder, vector_store, metadata)

    retriever = Retriever(fake_embedder, vector_store, metadata, tmp_config)
    eval_set = EvalSet(
        name="t",
        description="",
        samples=[EvalSample(query="zzz unrelated query", expected_doc_ids=["nonexistent-doc"])],
    )
    evaluator = RetrievalEvaluator(retriever=retriever, metadata=metadata)
    report = evaluator.run(eval_set, top_k=10)

    assert report.avg_mrr == pytest.approx(0.0)
    for v in report.avg_recall_at_k.values():
        assert v == pytest.approx(0.0)


def test_load_eval_set_json(tmp_path: Path):
    data = {
        "name": "test",
        "description": "d",
        "samples": [
            {"query": "q1", "expected_doc_ids": ["a"], "expected_doc_names": ["x.txt"]},
            {"query": "q2", "partition_filter": "P", "tag_filters": ["T"]},
        ],
    }
    p = tmp_path / "eval.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    es = load_eval_set(p)
    assert es.name == "test"
    assert len(es.samples) == 2
    assert es.samples[0].expected_doc_ids == ["a"]
    assert es.samples[1].partition_filter == "P"


def test_load_eval_set_format_errors(tmp_path: Path):
    p = tmp_path / "bad.json"
    p.write_text("[]", encoding="utf-8")
    with pytest.raises(EvalSetFormatError):
        load_eval_set(p)

    p2 = tmp_path / "bad2.json"
    p2.write_text(json.dumps({"name": "x", "samples": []}), encoding="utf-8")
    with pytest.raises(EvalSetFormatError):
        load_eval_set(p2)

    p3 = tmp_path / "bad3.json"
    p3.write_text(json.dumps({"name": "x", "samples": [{"foo": "bar"}]}), encoding="utf-8")
    with pytest.raises(EvalSetFormatError):
        load_eval_set(p3)


def test_save_and_print_report(tmp_path, tmp_config, fake_embedder, vector_store, metadata):
    doc_id, text = _seed_one_doc(tmp_config, fake_embedder, vector_store, metadata)
    retriever = Retriever(fake_embedder, vector_store, metadata, tmp_config)
    eval_set = EvalSet(
        name="t",
        description="",
        samples=[EvalSample(query=text, expected_doc_ids=[doc_id])],
    )
    evaluator = RetrievalEvaluator(retriever=retriever, metadata=metadata)
    report = evaluator.run(eval_set, top_k=5)

    out = tmp_path / "report.json"
    evaluator.save_report(report, out)
    loaded = json.loads(out.read_text("utf-8"))
    assert loaded["total_samples"] == 1
    assert loaded["avg_mrr"] == pytest.approx(1.0)
    assert len(loaded["sample_results"]) == 1

    evaluator.print_report(report)