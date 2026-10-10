# 内置字体目录

应用启动时会把本目录下的 `.ttf` / `.otf` 注册到 Qt 字体库（见 `../fonts.py`）。

目录默认**为空**：KVault 不捆绑任何字体文件，直接使用系统已安装字体
（界面字体见 `../variables.py` 的 `FONT_UI` / `FONT_MONO` / `FONT_CONTENT`）。

如需离线使用一致的排版效果，可将字体文件（需确认许可证允许再分发）放入本目录，
启动时会自动加载。例如 Inter、JetBrains Mono（均为 SIL Open Font License）。