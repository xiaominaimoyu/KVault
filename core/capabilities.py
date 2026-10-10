"""运行时能力探测。

回答一个问题：**在当前环境下，KVault 的哪些功能可用？**

KVault 的功能对本地模型的依赖是分层的：

============  ==========================================================
功能          是否需要嵌入模型
============  ==========================================================
笔记库        否——纯 Markdown 文件 + SQLite 索引
图谱 / 反链   否——纯链接解析
MCP 笔记读写  否——不经过检索
关键词检索    否——BM25 直接匹配倒排文本
语义检索      **是**——需要把查询与文档向量化
文档导入      **是**——切块后必须生成向量
============  ==========================================================

因此**没有本地推理框架时应用仍应完整启动**，只是语义相关能力受限。
本模块把��个判断集中在一处，供启动流程、状态栏与 UI 复用。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from core.startup_check import CheckResult, StartupChecker

logger = logging.getLogger(__name__)

#: 受限时受影响的功能标识
FEATURE_SEARCH = "search"
FEATURE_IMPORT = "import"


@dataclass
class Capabilities:
    """当前运行环境的可用能力。"""

    embedding_ready: bool
    """嵌入服务与模型是否就绪（决定语义检索与文档导入）。"""

    backend_type: str = "ollama"
    backend_name: str = ""

    reasons: list[str] = field(default_factory=list)
    """不可用时的原因说明，直接展示给用户。"""

    checks: list[CheckResult] = field(default_factory=list)
    """完整的启动检查结果，便于在 UI 中展示。"""

    @property
    def limited(self) -> bool:
        """是否处于受限模式（部分功能不可用）。"""
        return not self.embedding_ready

    @property
    def available_features(self) -> list[str]:
        """当前可用的功能列表。"""
        features = ["notes", "graph", "links", "keyword_search"]
        if self.embedding_ready:
            features.extend([FEATURE_SEARCH, FEATURE_IMPORT])
        return features

    @property
    def unavailable_features(self) -> list[str]:
        """当前不可用的功能列表。"""
        if self.embedding_ready:
            return []
        return [FEATURE_SEARCH, FEATURE_IMPORT]

    def summary(self) -> str:
        """一行摘要，用于日志与状态栏。"""
        if self.embedding_ready:
            return f"语义能力就绪（{self.backend_type}: {self.backend_name}）"
        return "受限模式：未配置本地模型，语义检索与文档导入不可用"

    def user_message(self) -> str:
        """面向用户的多行说明。"""
        if self.embedding_ready:
            return self.summary()
        lines = [
            "未检测到可用的本地嵌入模型，已进入受限模式。",
            "",
            "仍可使用：笔记库、图谱、反链、标签、MCP 笔记读写、关键词检索。",
            "不可用：语义检索、文档导入与重建索引。",
        ]
        if self.reasons:
            lines.append("")
            lines.append("原因：")
            lines.extend(f"· {reason}" for reason in self.reasons)
        lines.append("")
        lines.append(
            "配置方式：设置 → 模型，选择 Ollama 或 llama.cpp 后端；"
            "完成后点击状态栏的「重试检测」。"
        )
        return "\n".join(lines)


def probe(config) -> Capabilities:
    """探测当前配置下的运行时能力。

    该函数**永不抛异常**：任何探测失败都转化为受限模式。
    """
    backend = getattr(config, "embedding_backend", "ollama")
    try:
        checker = StartupChecker(config)
        results = checker.check_all()
    except Exception:  # noqa: BLE001 —— 探测失败不应阻止启动
        logger.warning("能力探测异常，按受限模式处理", exc_info=True)
        return Capabilities(
            embedding_ready=False,
            backend_type=backend,
            reasons=["启动检查执行异常"],
        )

    # 嵌入相关的检查项：后端不同，检查名称不同
    if backend == "llama_cpp":
        relevant = {"llama.cpp 依赖", "GGUF 模型"}
    else:
        relevant = {"Ollama 服务", "嵌入模型"}

    failed = [r for r in results if not r.passed and r.name in relevant]
    embedding_ready = not failed

    reasons = [f"{r.name}：{r.message}" for r in failed]

    backend_name = ""
    if embedding_ready:
        backend_name = _describe_backend(config)

    return Capabilities(
        embedding_ready=embedding_ready,
        backend_type=backend,
        backend_name=backend_name,
        reasons=reasons,
        checks=results,
    )


def _describe_backend(config) -> str:
    """返回当前后端的可读名称。"""
    if getattr(config, "embedding_backend", "ollama") == "llama_cpp":
        from pathlib import Path

        path = config.llama_cpp.model_path
        return Path(path).name if path else "GGUF"
    return config.embedding_model