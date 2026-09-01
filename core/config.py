import json
import os
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path


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
    top_k: int = 5
    similarity_threshold: float = 0.5
    mcp_enabled: bool = False
    theme: str = "system"
    last_index_model: str | None = None
    last_index_dimension: int | None = None
    last_index_at: float | None = None
    hybrid_search: HybridSearchConfig = field(default_factory=HybridSearchConfig)

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
        errors.extend(self.hybrid_search.validate())
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
        data = json.loads(config_path.read_text("utf-8")) if config_path.exists() else {}
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
