
from pathlib import Path
from core.config import Config, _resolve_path


def test_resolve_relative_path(tmp_path: Path):
    resolved = _resolve_path("./data/files", tmp_path)
    assert resolved == (tmp_path / "data" / "files").resolve()


def test_resolve_absolute_path(tmp_path: Path):
    abs_path = tmp_path / "abs"
    assert _resolve_path(abs_path, Path("/unused")) == abs_path


def test_config_load_creates_dirs(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg_path = tmp_path / "config.json"
    cfg = Config.load(str(cfg_path))
    assert cfg.files_dir.exists()
    assert cfg.chroma_dir.exists()
    assert cfg.logs_dir.exists()
