"""fonts 字体打包注册测试。"""

from pathlib import Path

from gui.styles.fonts import register_bundled_fonts

_FONTS_DIR = Path(__file__).resolve().parents[2] / "gui" / "styles" / "fonts"


def test_fonts_dir_exists():
    assert _FONTS_DIR.is_dir()


def test_register_no_fonts_is_safe(monkeypatch):
    """目录为空或不存在时不崩溃、不注册。"""
    monkeypatch.setattr("gui.styles.fonts.FONTS_DIR", None)
    assert register_bundled_fonts() == []


def test_register_calls_add_application_font(monkeypatch, tmp_path):
    calls = []

    class _FakeFontDb:
        @staticmethod
        def addApplicationFont(path):
            calls.append(path)
            return 0

    monkeypatch.setattr("gui.styles.fonts.FONTS_DIR", tmp_path)
    monkeypatch.setattr("gui.styles.fonts.QFontDatabase", _FakeFontDb)
    (tmp_path / "Inter-Regular.ttf").write_bytes(b"fake")
    (tmp_path / "JetBrainsMono-Regular.ttf").write_bytes(b"fake")

    registered = register_bundled_fonts()

    assert len(calls) == 2
    assert len(registered) == 2


def test_register_skips_failed_fonts(monkeypatch, tmp_path):
    class _FakeFontDb:
        @staticmethod
        def addApplicationFont(path):
            return -1 if "bad" in path else 0

    monkeypatch.setattr("gui.styles.fonts.FONTS_DIR", tmp_path)
    monkeypatch.setattr("gui.styles.fonts.QFontDatabase", _FakeFontDb)
    (tmp_path / "good.ttf").write_bytes(b"fake")
    (tmp_path / "bad.ttf").write_bytes(b"fake")

    registered = register_bundled_fonts()

    assert len(registered) == 1
