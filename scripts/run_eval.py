"""检索评测命令行入口。

用法:
    python scripts/run_eval.py --eval-set eval/sample.json --output eval/report.json
    python scripts/run_eval.py --eval-set eval/sample.json --mode hybrid --top-k 10

注意: --mode hybrid 需要 jieba 可选依赖（P1-5 实现后可用）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Config
from core.embedding_service import EmbeddingService
from core.evaluator import RetrievalEvaluator, load_eval_set
from core.metadata_manager import MetadataManager
from core.retriever import Retriever
from core.vector_store import VectorStore


def main() -> int:
    parser = argparse.ArgumentParser(description="KVault 检索质量评测")
    parser.add_argument("--eval-set", required=True, help="评测集文件路径 (JSON/YAML)")
    parser.add_argument("--output", default=None, help="报告输出路径 (JSON)")
    parser.add_argument(
        "--mode",
        choices=["vector", "hybrid"],
        default="vector",
        help="检索模式: vector=纯向量, hybrid=混合检索 (P1-5 后可用)",
    )
    parser.add_argument("--top-k", type=int, default=10, help="检索 Top-K")
    parser.add_argument("--config", default="config.json", help="配置文件路径")
    args = parser.parse_args()

    config = Config.load(args.config)
    vector_store = VectorStore(str(config.chroma_dir))
    metadata = MetadataManager(str(config.sqlite_path), vector_store=vector_store)
    embedder = EmbeddingService(
        model=config.embedding_model,
        base_url=config.ollama_base_url,
        batch_size=config.embedding_batch_size,
    )
    retriever = Retriever(
        embedder=embedder,
        vector_store=vector_store,
        metadata=metadata,
        config=config,
    )

    if args.mode == "hybrid":
        print("提示: hybrid 模式将在 P1-5 实现后可用，当前降级为 vector 模式")

    eval_set = load_eval_set(args.eval_set)
    evaluator = RetrievalEvaluator(retriever=retriever, metadata=metadata)
    report = evaluator.run(eval_set, top_k=args.top_k)

    evaluator.print_report(report)

    if args.output:
        evaluator.save_report(report, args.output)
        print(f"报告已保存至: {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())