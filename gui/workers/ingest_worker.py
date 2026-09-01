import os
from PySide6.QtCore import QThread, Signal


class IngestWorker(QThread):
    progress = Signal(int, str)
    file_done = Signal(str, bool, str, str)
    finished_all = Signal(int, int)

    def __init__(self, file_paths: list[str], ingest_fn):
        super().__init__()
        self.file_paths = file_paths
        self.ingest_fn = ingest_fn

    def run(self):
        total = len(self.file_paths)
        success = 0
        fail = 0
        for i, path in enumerate(self.file_paths, start=1):
            file_name = os.path.basename(path)
            self.progress.emit(int(i / total * 100), file_name)
            try:
                doc_id = self.ingest_fn(path)
                self.file_done.emit(doc_id, True, file_name, "")
                success += 1
            except Exception as e:
                self.file_done.emit("", False, file_name, str(e))
                fail += 1
        self.finished_all.emit(success, fail)
