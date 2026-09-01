import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from core.config import Config
from core.startup_check import StartupChecker
from gui.main_window import MainWindow
from gui.startup_dialog import StartupDialog


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


def _run_startup_check(config: Config) -> bool:
    """Run startup checks with retry loop. Requires QApplication to exist.

    Returns True if the app should continue (checks passed or user skipped).
    """
    checker = StartupChecker(config)
    while True:
        results = checker.check_all()
        for r in results:
            if r.passed:
                logging.info("Startup check [%s]: %s", r.name, r.message)
            else:
                logging.warning("Startup check [%s]: %s", r.name, r.message)

        if not checker.has_errors(results):
            return True

        dialog = StartupDialog(results)
        if dialog.exec() == StartupDialog.Accepted:
            # Retry: re-run checks
            logging.info("User requested startup check retry")
            continue
        # Skip and continue
        logging.info("User skipped startup check")
        return True


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

    if not _run_startup_check(config):
        logging.info("Startup aborted")
        return

    window = MainWindow(config)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
