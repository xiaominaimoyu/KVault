import json
import logging
import os
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class HybridSearchConfig:
    """混合检索配置。"""

    enabled: bool = False
    strategy: str = "rrf"
    bm25_weight: float = 0.5
    vector_weight: float = 0.5
    rrf_k: int = 60

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.strategy not in ("rrf", "weighted_norm"):
            errors.append(f"hybrid_search.strategy must be 'rrf' or 'weighted_norm', got '{self.strategy}'")
        if self.bm25_weight < 0 or self.vector_weight < 0:
            errors.append("hybrid_search weights must be non-negative")
        if self.bm25_weight + self.vector_weight <= 0:
            errors.append("hybrid_search weights sum must be > 0")
        if self.rrf_k <= 0:
            errors.append(f"hybrid_search.rrf_k must be > 0, got {self.rrf_k}")
        return errors


@dataclass
class WorkspaceItem:
    """单个工作区元数据。"""

    id: str
    name: str
    created_at: float = field(default_factory=time.time)


@dataclass
class WorkspaceConfig:
    """工作区配置段。"""

    current: str = "default"
    items: list[WorkspaceItem] = field(default_factory=lambda: [WorkspaceItem(id="default", name="默认工作区")])

    def validate(self) -> list[str]:
        errors: list[str] = []
        ids = [ws.id for ws in self.items]
        if len(ids) != len(set(ids)):
            errors.append("workspace ids must be unique")
        for ws in self.items:
            if not ws.name.strip():
                errors.append(f"workspace '{ws.id}' name must not be empty")
        if self.current and self.current not in ids:
            errors.append(f"workspaces.current '{self.current}' not found in items")
        return errors

    def get_item(self, ws_id: str) -> WorkspaceItem | None:
        for ws in self.items:
            if ws.id == ws_id:
                return ws
        return None


@dataclass
class LlamaCppConfig:
    """llama.cpp 后端配置。"""

    model_path: str = ""
    n_gpu_layers: int = 0
    n_ctx: int = 2048
    embedding_dim: int | None = None

    def validate(self, backend: str) -> list[str]:
        errors: list[str] = []
        if backend != "llama_cpp":
            return errors
        if not self.model_path.strip():
            errors.append("llama_cpp.model_path must not be empty when backend is llama_cpp")
        if self.n_gpu_layers < 0:
            errors.append(f"llama_cpp.n_gpu_layers must be >= 0, got {self.n_gpu_layers}")
        if self.n_ctx < 512:
            errors.append(f"llama_cpp.n_ctx must be >= 512, got {self.n_ctx}")
        return errors


@dataclass
class Config:
    files_dir: Path = Path("./data/files")
    chroma_dir: Path = Path("./data/chroma_db")
    sqlite_path: Path = Path("./data/kb.sqlite")
    logs_dir: Path = Path("./data/logs")
    chunk_size: int = 500
    chunk_overlap: int = 100
    embedding_model: str = "bge-large-zh-v1.5"
    ollama_base_url: str = "http://localhost:11434"
    embedding_batch_size: int = 32
    embedding_backend: str = "ollama"
    llama_cpp: LlamaCppConfig = field(default_factory=LlamaCppConfig)
    top_k: int = 5
    similarity_threshold: float = 0.5
    mcp_enabled: bool = False
    theme: str = "system"
    reduce_motion: bool = False
    """是否禁用全部界面动效（对应系统级 prefers-reduced-motion）。

    设计文档 6.1 要求该配置项；GUI 重设计文档 10.2 声称不改``core``，
    但两者冲突——动效规范没有这个字段就无法落地，因此以 6.1 为准。
    ``gui/widgets/motion.py`` 与 ``StatusDot`` 的脉动动画均读取此值。
    """

    #: 文档列表视图模式：``"table"``（列表）/ ``"grid"``（卡片）
    #: 对应设计文档 3.3.3「记忆用户选择到 config」
    view_mode: str = "table"

    last_index_model: str | None = None
    last_index_dimension: int | None = None
    last_index_at: float | None = None
    hybrid_search: HybridSearchConfig = field(default_factory=HybridSearchConfig)
    workspaces: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    connectors: list[dict] = field(default_factory=list)

    def validate(self) -> list[str]:
        """Validate config fields and return a list of error messages.

        An empty list means the config is valid. Checks cover chunking
        parameters (chunk_size > 0 and 0 <= chunk_overlap < chunk_size)
        and similarity threshold range.
        """
        errors: list[str] = []
        if self.chunk_size <= 0:
            errors.append(f"chunk_size must be > 0, got {self.chunk_size}")
        if self.chunk_overlap < 0:
            errors.append(f"chunk_overlap must be >= 0, got {self.chunk_overlap}")
        if self.chunk_overlap >= self.chunk_size:
            errors.append(
                f"chunk_overlap ({self.chunk_overlap}) must be < chunk_size ({self.chunk_size})"
            )
        if not 0 <= self.similarity_threshold <= 1:
            errors.append(
                f"similarity_threshold must be between 0 and 1, got {self.similarity_threshold}"
            )
        if self.top_k <= 0:
            errors.append(f"top_k must be > 0, got {self.top_k}")
        if self.view_mode not in ("table", "grid"):
            errors.append(
                f"view_mode must be 'table' or 'grid', got '{self.view_mode}'"
            )
        errors.extend(self.hybrid_search.validate())
        errors.extend(self.workspaces.validate())
        if self.embedding_backend not in ("ollama", "llama_cpp"):
            errors.append(
                f"embedding_backend must be 'ollama' or 'llama_cpp', got '{self.embedding_backend}'"
            )
        errors.extend(self.llama_cpp.validate(self.embedding_backend))
        valid_connector_types = {"local_dir", "github", "notion", "feishu"}
        for i, c in enumerate(self.connectors):
            if not isinstance(c, dict):
                errors.append(f"connectors[{i}] must be a dict")
                continue
            ctype = c.get("type", "")
            if ctype not in valid_connector_types:
                errors.append(
                    f"connectors[{i}].type must be one of {valid_connector_types}, got '{ctype}'"
                )
            if not c.get("name", "").strip():
                errors.append(f"connectors[{i}].name must not be empty")
        return errors

    def to_dict(self) -> dict:
        d = {}
        for k, v in asdict(self).items():
            if isinstance(v, Path):
                d[k] = str(v)
            else:
                d[k] = v
        return d

    @classmethod
    def load(cls, path: str = "config.json") -> "Config":
        config_path = _resolve_config_path(path)
        data = _read_config_json(config_path)
        base_dir = _data_base_dir()

        # Resolve relative path fields against the chosen data base directory
        for key in ("files_dir", "chroma_dir", "sqlite_path", "logs_dir"):
            if key in data and isinstance(data[key], str):
                data[key] = _resolve_path(data[key], base_dir)
            elif key not in data:
                data[key] = _resolve_path(getattr(cls, key), base_dir)

        # Parse nested hybrid_search config
        if "hybrid_search" in data and isinstance(data["hybrid_search"], dict):
            data["hybrid_search"] = HybridSearchConfig(**data["hybrid_search"])

        # Parse nested workspaces config
        if "workspaces" in data and isinstance(data["workspaces"], dict):
            ws_data = data["workspaces"]
            items = [
                WorkspaceItem(**item) for item in ws_data.get("items", [])
            ]
            data["workspaces"] = WorkspaceConfig(
                current=ws_data.get("current", "default"),
                items=items or [WorkspaceItem(id="default", name="默认工作区")],
            )

        # Parse nested llama_cpp config
        if "llama_cpp" in data and isinstance(data["llama_cpp"], dict):
            data["llama_cpp"] = LlamaCppConfig(**data["llama_cpp"])

        cfg = cls(**data)
        cfg.files_dir.mkdir(parents=True, exist_ok=True)
        cfg.chroma_dir.mkdir(parents=True, exist_ok=True)
        cfg.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        cfg.logs_dir.mkdir(parents=True, exist_ok=True)
        return cfg

    def save(self, path: str = "config.json"):
        config_path = _resolve_config_path(path)
        config_path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )


def _read_config_json(config_path: Path) -> dict:
    """读取配置文件，任何损坏都不得阻止程序启动。

    实际遇到过的两类真实故障：
    - **BOM**：Windows 记事本、PowerShell ``Out-File -Encoding utf8`` 与部分
      编辑器都会写入 UTF-8 BOM。用 ``utf-8`` 读取会抛
      ``JSONDecodeError: Unexpected UTF-8 BOM``，直接让应用在启动时崩溃。
    - **内容损坏**：手工编辑中途保存，或磁盘写入被中断，得到非法 JSON。

    两种情况都退回到默认配置并记录警告——配置坏了应该降级，
    而不是让用户连程序都打不开。
    """
    if not config_path.exists():
        return {}

    try:
        # utf-8-sig 对有无 BOM 的文件都能正确解析
        raw = config_path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        logger.warning("无法读取配置文件 %s: %s，使用默认配置", config_path, exc)
        return {}

    if not raw.strip():
        return {}

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning(
            "配置文件 %s 不是合法 JSON (%s)，已忽略并使用默认配置。"
            "如需自定义可删除该文件后通过设置界面重新配置。",
            config_path,
            exc,
        )
        return {}

    if not isinstance(data, dict):
        logger.warning("配置文件 %s 顶层应为对象，使用默认配置", config_path)
        return {}

    return data


def _resolve_config_path(path: str) -> Path:
    """Resolve the config file path relative to the application base directory.

    Prevents config.json from being created in different locations depending on
    the current working directory at launch.
    """
    p = Path(path)
    if p.is_absolute():
        return p
    return (app_base_dir() / p).resolve()


def app_base_dir() -> Path:
    """Return the directory where the application executable/script resides."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _data_base_dir() -> Path:
    """Return the root directory for user data.

    In a packaged environment, prefer %APPDATA%\\KVault so that the executable
    directory stays read-only. In development, use the project root.
    """
    if getattr(sys, "frozen", False):
        appdata = os.getenv("APPDATA")
        if appdata:
            return Path(appdata) / "KVault"
        return app_base_dir() / "data"
    return app_base_dir()


def _resolve_path(value: str | Path, base_dir: Path) -> Path:
    p = Path(value)
    if p.is_absolute():
        return p
    return (base_dir / p).resolve()
