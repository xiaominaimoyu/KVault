
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


# --------------------------------------------------- 损坏配置不得阻止启动


def test_load_config_with_utf8_bom(tmp_path: Path):
    """带 BOM 的配置必须能正常读取。

    回归防护：Windows 记事本、PowerShell ``Out-File -Encoding utf8`` 以及
    不少编辑器都会写入 UTF-8 BOM。此前用 ``read_text("utf-8")`` 读取会抛
    ``JSONDecodeError: Unexpected UTF-8 BOM``，导致程序启动即崩溃。
    """
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text('{"chunk_size": 777}', encoding="utf-8-sig")
    assert Config.load(str(cfg_path)).chunk_size == 777


def test_load_config_with_malformed_json_falls_back(tmp_path: Path):
    """非法 JSON 必须降级为默认配置，而不是抛异常。"""
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text('{"chunk_size": ', encoding="utf-8")
    assert Config.load(str(cfg_path)).chunk_size == Config().chunk_size


def test_load_config_with_non_object_toplevel(tmp_path: Path):
    """顶层不是对象（数组/标量）时必须降级。"""
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text("[1, 2, 3]", encoding="utf-8")
    assert Config.load(str(cfg_path)).chunk_size == Config().chunk_size


def test_load_config_with_blank_content(tmp_path: Path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text("   \n  ", encoding="utf-8")
    assert Config.load(str(cfg_path)).chunk_size == Config().chunk_size


def test_load_config_missing_file_returns_defaults(tmp_path: Path):
    cfg = Config.load(str(tmp_path / "nope.json"))
    assert cfg.chunk_size == Config().chunk_size
