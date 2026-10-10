import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from core.capabilities import probe
from core.config import Config
from gui.main_window import MainWindow


def _setup_logging(logs_dir: Path):
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "app.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def _log_capabilities(caps) -> None:
    """把能力探测结果写入日志。"""
    for result in caps.checks:
        if result.passed:
            logging.info("Startup check [%s]: %s", result.name, result.message)
        else:
            logging.warning("Startup check [%s]: %s", result.name, result.message)

    if caps.limited:
        # 受限不是致命错误——笔记库等核心功能不依赖模型
        logging.warning("Running in LIMITED MODE: %s", caps.summary())
        for reason in caps.reasons:
            logging.warning("  - %s", reason)
    else:
        logging.info("Capabilities: %s", caps.summary())


def main():
    config = Config.load()
    _setup_logging(config.logs_dir)
    logging.info("KVault starting")
    logging.info(
        "Data paths: files_dir=%s chroma_dir=%s sqlite_path=%s logs_dir=%s",
        config.files_dir,
        config.chroma_dir,
        config.sqlite_path,
        config.logs_dir,
    )

    # QApplication must be created before any QDialog
    app = QApplication(sys.argv)

    # 探测运行时能力。**失败不阻断启动**——KVault 的笔记库、图谱、反链、
    # 标签与 MCP 笔记读写都不依赖本地模型；只有语义检索与文档导入需要。
    # 未配置模型时进入受限模式，由 UI 提示用户后续配置。
    capabilities = probe(config)
    _log_capabilities(capabilities)

    window = MainWindow(config, capabilities=capabilities)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()