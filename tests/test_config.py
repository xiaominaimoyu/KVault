
import json
from pathlib import Path

from core.config import AppearanceConfig, Config, _resolve_path


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


# ---- 外观配置 ----

def test_appearance_defaults():
    cfg = Config()
    assert isinstance(cfg.appearance, AppearanceConfig)
    assert cfg.appearance.accent_preset == "vault-teal"
    assert cfg.appearance.background_mode == "default"
    assert cfg.appearance.background_fit == "cover"


def test_appearance_validate_accepts_defaults():
    cfg = Config()
    assert cfg.validate() == []


def test_appearance_validate_rejects_bad_mode():
    cfg = Config()
    cfg.appearance.background_mode = "video"
    assert any("background_mode" in e for e in cfg.validate())


def test_appearance_validate_rejects_bad_fit():
    cfg = Config()
    cfg.appearance.background_fit = "stretch"
    assert any("background_fit" in e for e in cfg.validate())


def test_appearance_validate_rejects_bad_color():
    cfg = Config()
    cfg.appearance.background_mode = "color"
    cfg.appearance.background_color = "red"
    assert any("background_color" in e for e in cfg.validate())


def test_appearance_validate_rejects_out_of_range_alpha():
    cfg = Config()
    cfg.appearance.surface_alpha = 1.5
    assert any("surface_alpha" in e for e in cfg.validate())

    cfg = Config()
    cfg.appearance.background_overlay = -0.1
    assert any("background_overlay" in e for e in cfg.validate())


def test_appearance_validate_requires_existing_image(tmp_path: Path):
    cfg = Config()
    cfg.appearance.background_mode = "image"
    cfg.appearance.background_image = str(tmp_path / "missing.png")
    assert any("background_image" in e for e in cfg.validate())

    image = tmp_path / "bg.png"
    image.write_bytes(b"fake")
    cfg.appearance.background_image = str(image)
    assert cfg.validate() == []


def test_config_load_without_appearance_is_compatible(tmp_path: Path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text("{}", encoding="utf-8")
    cfg = Config.load(str(cfg_path))
    assert cfg.appearance == AppearanceConfig()


def test_config_roundtrip_appearance(tmp_path: Path):
    cfg = Config(
        files_dir=tmp_path / "files",
        chroma_dir=tmp_path / "chroma",
        sqlite_path=tmp_path / "kb.sqlite",
        logs_dir=tmp_path / "logs",
    )
    cfg.appearance = AppearanceConfig(
        accent_preset="rose",
        background_mode="color",
        background_color="#112233",
    )
    cfg_path = tmp_path / "config.json"
    cfg.save(str(cfg_path))

    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert raw["appearance"]["accent_preset"] == "rose"

    loaded = Config.load(str(cfg_path))
    assert loaded.appearance.accent_preset == "rose"
    assert loaded.appearance.background_color == "#112233"
