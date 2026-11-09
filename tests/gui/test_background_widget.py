"""背景绘制组件测试。"""

from pathlib import Path

from PySide6.QtCore import QRect, QSize
from PySide6.QtGui import QColor, QPixmap

from gui.widgets.background import BackgroundWidget, compute_draw_rect


def test_compute_cover_rect_crops_to_fill():
    rect = compute_draw_rect("cover", QSize(400, 200), QSize(200, 200))
    assert isinstance(rect, QRect)
    assert rect.width() >= 200
    assert rect.height() >= 200


def test_compute_contain_rect_fits_inside():
    rect = compute_draw_rect("contain", QSize(400, 200), QSize(200, 200))
    assert rect.width() <= 200
    assert rect.height() <= 200


def test_compute_tile_rect_equals_widget():
    rect = compute_draw_rect("tile", QSize(400, 200), QSize(200, 120))
    assert rect.size() == QSize(200, 120)


def test_default_appearance_paints_without_error(qapp):
    widget = BackgroundWidget()
    widget.resize(300, 200)
    pixmap = QPixmap(300, 200)
    widget.render(pixmap)
    assert not pixmap.isNull()


def test_solid_color_appearance(qapp):
    widget = BackgroundWidget()
    widget.set_appearance(mode="color", color="#123456")
    widget.resize(120, 80)
    pixmap = QPixmap(120, 80)
    widget.render(pixmap)
    assert not pixmap.isNull()


def test_missing_image_falls_back_to_color(qapp, tmp_path: Path):
    widget = BackgroundWidget()
    widget.set_appearance(
        mode="image", color="#101010", image_path=str(tmp_path / "missing.png")
    )
    widget.resize(100, 100)
    pixmap = QPixmap(100, 100)
    widget.render(pixmap)
    assert not pixmap.isNull()
    assert widget.image_loaded() is False


def test_existing_image_loads(qapp, tmp_path: Path):
    image_path = tmp_path / "bg.png"
    pixmap = QPixmap(20, 10)
    pixmap.fill(QColor("#336699"))
    assert pixmap.save(str(image_path))

    widget = BackgroundWidget()
    widget.set_appearance(mode="image", image_path=str(image_path))
    assert widget.image_loaded() is True
