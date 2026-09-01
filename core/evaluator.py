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