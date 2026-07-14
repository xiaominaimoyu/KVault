import json
import os
import sys
from dataclasses import dataclass, asdict
from pathlib import Path


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

    def to_dict(self) -> dict:
        return {k: str(v) if isinstance(v, Path) else v for k, v in asdict(self).items()}

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
