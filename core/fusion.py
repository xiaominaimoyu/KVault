"""检索结果融合模块，提供 RRF 与加权归一化两种策略。"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FusedResult:
    """融合后的单条结果。"""

    chunk_id: str
    score: float
    source_rank: int


def rrf(
    rankings: list[list[str]],
    weights: list[float] | None = None,
    k: int = 60,
) -> list[FusedResult]:
    """Reciprocal Rank Fusion。

    Args:
        rankings: 多路排名，每路是一个 chunk_id 列表（按相关性降序）。
        weights: 每路的权重，默认等权。
        k: RRF 平滑常数。

    Returns:
        融合后的结果列表（按融合分数降序）。
    """
    if not rankings:
        return []
    n = len(rankings)
    if weights is None:
        weights = [1.0 / n] * n
    if len(weights) != n:
        logger.warning("weights length %d != rankings %d, using equal weights", len(weights), n)
        weights = [1.0 / n] * n

    scores: dict[str, float] = {}
    for i, ranking in enumerate(rankings):
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + weights[i] / (k + rank)

    sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [
        FusedResult(chunk_id=cid, score=score, source_rank=rank + 1)
        for rank, (cid, score) in enumerate(sorted_items)
    ]


def weighted_norm(
    score_lists: list[list[tuple[str, float]]],
    weights: list[float] | None = None,
) -> list[FusedResult]:
    """加权归一化融合。

    Args:
        score_lists: 多路评分列表，每路是 (chunk_id, score) 元组列表。
        weights: 每路的权重，默认等权。

    Returns:
        融合后的结果列表（按融合分数降序）。
    """
    if not score_lists:
        return []
    n = len(score_lists)
    if weights is None:
        weights = [1.0 / n] * n
    if len(weights) != n:
        logger.warning("weights length %d != score_lists %d, using equal weights", len(weights), n)
        weights = [1.0 / n] * n

    norm_lists: list[dict[str, float]] = []
    for sl in score_lists:
        if not sl:
            norm_lists.append({})
            continue
        max_s = max(s for _, s in sl) or 1.0
        min_s = min(s for _, s in sl)
        denom = (max_s - min_s) or 1.0
        norm_lists.append({cid: (s - min_s) / denom for cid, s in sl})

    scores: dict[str, float] = {}
    for i, norm in enumerate(norm_lists):
        for cid, s in norm.items():
            scores[cid] = scores.get(cid, 0.0) + weights[i] * s

    sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [
        FusedResult(chunk_id=cid, score=score, source_rank=rank + 1)
        for rank, (cid, score) in enumerate(sorted_items)
    ]