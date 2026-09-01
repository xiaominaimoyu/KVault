
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


def test_validate_chunk_params():
    cfg = Config()
    assert cfg.validate() == []

    cfg.chunk_size = 0
    assert any("chunk_size" in e for e in cfg.validate())

    cfg.chunk_size = -10
    assert any("chunk_size" in e for e in cfg.validate())

    cfg = Config()
    cfg.chunk_overlap = -1
    assert any("chunk_overlap" in e for e in cfg.validate())

    cfg = Config()
    cfg.chunk_overlap = cfg.chunk_size
    assert any("chunk_overlap" in e for e in cfg.validate())

    cfg = Config()
    cfg.chunk_overlap = cfg.chunk_size + 100
    errors = cfg.validate()
    assert any("chunk_overlap" in e for e in errors)

    cfg = Config()
    cfg.similarity_threshold = 1.5
    assert any("similarity_threshold" in e for e in cfg.validate())

    cfg = Config()
    cfg.similarity_threshold = -0.1
    assert any("similarity_threshold" in e for e in cfg.validate())

    cfg = Config()
    cfg.top_k = 0
    assert any("top_k" in e for e in cfg.validate())

    cfg = Config(chunk_size=200, chunk_overlap=50, top_k=10, similarity_threshold=0.3)
    assert cfg.validate() == []
