"""字体打包注册。

Inter / JetBrains Mono 打包到 `gui/styles/fonts/`，
启动时通过 QFontDatabase.addApplicationFont() 注册；
衬线正文使用系统已安装字体，不打包。
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtGui import QFontDatabase

logger = logging.getLogger(__name__)

_FONTS_DIR = Path(__file__).parent / "fonts"
FONTS_DIR = _FONTS_DIR if _FONTS_DIR.is_dir() else None

_FONT_EXTENSIONS = ("*.ttf", "*.otf")


def register_bundled_fonts() -> list[str]:
    """注册打包目录中的全部字体文件。

    Returns:
        注册成功的字体文件路径列表；
        目录不存在或为空时返回空列表。
    """
    if FONTS_DIR is None:
        return []

    font_files: list[Path] = []
    for pattern in _FONT_EXTENSIONS:
        font_files.extend(FONTS_DIR.glob(pattern))
    font_files.sort()

    registered: list[str] = []
    for font_file in font_files:
        font_id = QFontDatabase.addApplicationFont(str(font_file))
        if font_id >= 0:
            registered.append(str(font_file))
        else:
            logger.warning("字体注册失败: %s", font_file)
    return registered
