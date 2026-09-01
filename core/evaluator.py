"""检索质量评测模块。

提供评测集加载、Recall@K / MRR 计算与报告输出能力。
评测集格式支持 JSON 与 YAML（YAML 需可选安装 pyyaml）。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.retriever import Retriever
    from core.metadata_manager import MetadataManager

logger = logging.getLogger(__name__)

_K_VALUES = (1, 3, 5, 10)


@dataclass
class EvalSample:
    """单条评测样本。"""

    query: str
    expected_doc_ids: list[str] = field(default_factory=list)
    expected_doc_names: list[str] = field(default_factory=list)
    partition_filter: str | None = None
    tag_filters: list[str] = field(default_factory=list)


@dataclass
class SampleResult:
    """单条样本的评估结果。"""

    query: str
    hit_doc_ids: list[str]
    hit_ranks: list[int]
    recall_at_k: dict[int, float]
    mrr: float
    expected_count: int
    retrieved_count: int


@dataclass
class EvalReport:
    """整份评测集的汇总报告。"""

    name: str
    total_samples: int
    hit_samples: int
    avg_recall_at_k: dict[int, float]
    avg_mrr: float
    sample_results: list[SampleResult]
    top_k: int


@dataclass
class EvalSet:
    """评测集容器。"""

    name: str
    description: str
    samples: list[EvalSample]


class EvalSetFormatError(ValueError):
    """评测集格式错误。"""


def load_eval_set(path: str | Path) -> EvalSet:
    """从 JSON 或 YAML 文件加载评测集。

    Args:
        path: 评测集文件路径。.yaml/.yml 后缀使用 YAML 解析，其余用 JSON。

    Raises:
        EvalSetFormatError: 评测集格式不合法或字段缺失。
        FileNotFoundError: 文件不存在。
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"评测集文件不存在: {p}")

    suffix = p.suffix.lower()
    if suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError:
            raise EvalSetFormatError(
                "YAML 评测集需要 pyyaml，请 pip install pyyaml；或使用 JSON 格式"
            )
        data = yaml.safe_load(p.read_text("utf-8"))
    else:
        data = json.loads(p.read_text("utf-8"))

    if not isinstance(data, dict):
        raise EvalSetFormatError("评测集根节点必须是对象")

    name = data.get("name", "unnamed")
    description = data.get("description", "")
    raw_samples = data.get("samples")
    if not isinstance(raw_samples, list) or not raw_samples:
        raise EvalSetFormatError("评测集必须包含非空 samples 数组")

    samples: list[EvalSample] = []
    for i, raw in enumerate(raw_samples):
        if not isinstance(raw, dict):
            raise EvalSetFormatError(f"sample[{i}] 必须是对象")
        query = raw.get("query")
        if not query or not str(query).strip():
            raise EvalSetFormatError(f"sample[{i}] 缺少非空 query")
        samples.append(
            EvalSample(
                query=str(query),
                expected_doc_ids=list(raw.get("expected_doc_ids", [])),
                expected_doc_names=list(raw.get("expected_doc_names", [])),
                partition_filter=raw.get("partition_filter"),
                tag_filters=list(raw.get("tag_filters", [])),
            )
        )

    return EvalSet(name=name, description=description, samples=samples)


class RetrievalEvaluator:
    """检索质量评测器，计算 Recall@K 与 MRR。"""

    def __init__(self, retriever: "Retriever", metadata: "MetadataManager"):
        self.retriever = retriever
        self.metadata = metadata

    def _resolve_expected_doc_ids(self, sample: EvalSample) -> set[str]:
        """将 expected_doc_names 解析为 doc_id 集合，与 expected_doc_ids 合并。"""
        expected = set(sample.expected_doc_ids)
        if not sample.expected_doc_names:
            return expected
        name_set = {n.lower() for n in sample.expected_doc_names}
        for doc in self.metadata.list_documents():
            if doc.file_name.lower() in name_set:
                expected.add(doc.id)
        return expected

    def _build_filters(self, sample: EvalSample) -> dict | None:
        """根据 partition_filter / tag_filters 构建 ChromaDB where 过滤条件。"""
        if not sample.partition_filter and not sample.tag_filters:
            return None

        candidates: set[str] | None = None

        if sample.partition_filter:
            partition_doc_ids: set[str] = set()
            for doc in self.metadata.list_documents():
                if doc.partition_name == sample.partition_filter:
                    partition_doc_ids.add(doc.id)
            candidates = partition_doc_ids

        if sample.tag_filters:
            tag_name_set = {t.lower() for t in sample.tag_filters}
            tag_doc_ids: set[str] = set()
            all_docs = self.metadata.list_documents()
            all_doc_ids = [d.id for d in all_docs]
            tag_map = self.metadata.get_documents_tag_map(all_doc_ids)
            for doc_id, tags in tag_map.items():
                tag_names = {t.get("name", "").lower() for t in tags}
                if tag_name_set & tag_names:
                    tag_doc_ids.add(doc_id)
            candidates = tag_doc_ids if candidates is None else (candidates & tag_doc_ids)

        if not candidates:
            return {"document_id": {"$in": []}}

        return {"document_id": {"$in": sorted(candidates)}}

    def run(self, eval_set: EvalSet, top_k: int = 10) -> EvalReport:
        """逐条执行评测样本，计算 Recall@K 与 MRR。

        评测过程只读，不修改知识库向量与元数据。
        """
        k_values = [k for k in _K_VALUES if k <= top_k]
        if not k_values:
            k_values = [top_k]

        sample_results: list[SampleResult] = []
        recall_sums: dict[int, float] = {k: 0.0 for k in k_values}
        mrr_sum = 0.0
        hit_count = 0

        for sample in eval_set.samples:
            expected_ids = self._resolve_expected_doc_ids(sample)
            filters = self._build_filters(sample)
            results = self.retriever.search(
                query=sample.query, top_k=top_k, filters=filters
            )

            retrieved_doc_ids = [r.document_id for r in results]
            hit_doc_ids: list[str] = []
            hit_ranks: list[int] = []
            for rank, doc_id in enumerate(retrieved_doc_ids, start=1):
                if doc_id and doc_id in expected_ids:
                    hit_doc_ids.append(doc_id)
                    hit_ranks.append(rank)

            recall_at_k: dict[int, float] = {}
            for k in k_values:
                topk_docs = retrieved_doc_ids[:k]
                hits = sum(1 for d in topk_docs if d and d in expected_ids)
                recall_at_k[k] = hits / len(expected_ids) if expected_ids else 0.0
                recall_sums[k] += recall_at_k[k]

            mrr = 1.0 / hit_ranks[0] if hit_ranks else 0.0
            mrr_sum += mrr

            if hit_doc_ids:
                hit_count += 1

            sample_results.append(
                SampleResult(
                    query=sample.query,
                    hit_doc_ids=hit_doc_ids,
                    hit_ranks=hit_ranks,
                    recall_at_k=recall_at_k,
                    mrr=mrr,
                    expected_count=len(expected_ids),
                    retrieved_count=len(retrieved_doc_ids),
                )
            )

        total = len(eval_set.samples)
        avg_recall = {k: (recall_sums[k] / total if total else 0.0) for k in k_values}
        avg_mrr = mrr_sum / total if total else 0.0

        return EvalReport(
            name=eval_set.name,
            total_samples=total,
            hit_samples=hit_count,
            avg_recall_at_k=avg_recall,
            avg_mrr=avg_mrr,
            sample_results=sample_results,
            top_k=top_k,
        )
