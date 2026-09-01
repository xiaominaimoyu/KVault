from __future__ import annotations

from core.fusion import rrf, weighted_norm


def test_rrf_basic():
    ranking_a = ["c1", "c2", "c3"]
    ranking_b = ["c2", "c1", "c4"]
    results = rrf([ranking_a, ranking_b], k=60)
    assert len(results) == 4
    ids = {r.chunk_id for r in results}
    assert ids == {"c1", "c2", "c3", "c4"}
    c2_score = next(r.score for r in results if r.chunk_id == "c2")
    c3_score = next(r.score for r in results if r.chunk_id == "c3")
    assert c2_score > c3_score


def test_rrf_empty():
    assert rrf([]) == []


def test_rrf_weights():
    ranking_a = ["c1", "c2"]
    ranking_b = ["c2", "c1"]
    results_equal = rrf([ranking_a, ranking_b], weights=[0.5, 0.5])
    results_weighted = rrf([ranking_a, ranking_b], weights=[0.9, 0.1])
    assert len(results_equal) == 2
    assert len(results_weighted) == 2


def test_weighted_norm_basic():
    list_a = [("c1", 0.9), ("c2", 0.5)]
    list_b = [("c2", 0.8), ("c1", 0.3)]
    results = weighted_norm([list_a, list_b])
    assert len(results) == 2
    assert results[0].chunk_id in ("c1", "c2")


def test_weighted_norm_empty():
    assert weighted_norm([]) == []