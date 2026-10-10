"""生成 KVault 应用图标 assets/kvault.ico。

沿用 Vault Standard 主色（``#2DD4BF``），深色底呼应「保险库」意象。
用 PySide6 绘制后交给 Qt 输出多尺寸 ico，避免引入 Pillow 依赖。

用法::

    python scripts/make_icon.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

OUT_DIR = Path(__file__).resolve().parent.parent / "assets"
OUT_FILE = OUT_DIR / "kvault.ico"

# Vault Standard
BG = QColor("#0F1115")
ACCENT = QColor("#2DD4BF")
WARM = QColor("#F5A623")

SIZES = [16, 24, 32, 48, 64, 128, 256]


def render(size: int) -> QPixmap:
    """绘制单个尺寸的图标。"""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)

    # 圆角深色底
    radius = size * 0.22
    painter.setPen(Qt.NoPen)
    painter.setBrush(BG)
    painter.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)

    # 主色内描边
    pen_width = max(1.0, size * 0.045)
    painter.setPen(Qt.NoPen)
    painter.setBrush(ACCENT)
    inset = size * 0.16
    painter.drawRoundedRect(
        QRectF(inset, inset, size - inset * 2, size - inset * 2),
        radius * 0.7,
        radius * 0.7,
    )

    # 字母 K（深色，压在主色块上）
    font = QFont("Segoe UI", max(6, int(size * 0.52)))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#0F1115"))
    painter.drawText(
        QRectF(0, 0, size, size), Qt.AlignCenter, "K"
    )

    # 右下角暖色高光点，呼应「内容之光」
    dot = size * 0.13
    painter.setBrush(WARM)
    painter.drawEllipse(
        QRectF(size - dot * 2.1, size - dot * 2.1, dot, dot)
    )

    painter.end()
    return pixmap


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # PySide6 无法直接写多分辨率 ico，这里手动拼接 ICO 容器
    images = [render(size).toImage() for size in SIZES]
    _write_ico(OUT_FILE, images)

    print(f"icon written: {OUT_FILE} ({OUT_FILE.stat().st_size} bytes)")
    del app
    return 0


def _png_bytes(image: QImage) -> bytes:
    """把 QImage 编码为 PNG 字节串。"""
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def _write_ico(path: Path, images: list[QImage]) -> None:
    """写出多分辨率 ICO 文件（PNG 压缩条目，Vista+ 通用）。"""
    payloads = [_png_bytes(image) for image in images]

    header = bytearray()
    # ICONDIR
    header += (0).to_bytes(2, "little")  # reserved
    header += (1).to_bytes(2, "little")  # type = icon
    header += len(images).to_bytes(2, "little")

    # ICONDIRENTRY 数组（先占位，稍后回填偏移）
    entries = bytearray()
    offset = 6 + 16 * len(images)

    for image, payload in zip(images, payloads):
        width = image.width() if image.width() < 256 else 0
        height = image.height() if image.height() < 256 else 0
        entries += bytes([width, height, 0, 0])  # 宽高、颜色数、保留
        entries += (1).to_bytes(2, "little")  # color planes
        entries += (32).to_bytes(2, "little")  # bits per pixel
        entries += len(payload).to_bytes(4, "little")
        entries += offset.to_bytes(4, "little")
        offset += len(payload)

    with path.open("wb") as handle:
        handle.write(header + entries)
        for payload in payloads:
            handle.write(payload)


if __name__ == "__main__":
    raise SystemExit(main())