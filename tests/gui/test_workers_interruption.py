"""导入/重索引 worker 的中断响应测试。"""

from gui.workers.ingest_worker import IngestWorker


def test_ingest_worker_stops_when_interrupted(monkeypatch):
    processed: list[str] = []

    worker = IngestWorker(
        file_paths=[f"file-{i}.txt" for i in range(50)],
        ingest_fn=lambda path: processed.append(path) or "doc",
    )
    # QThread.start() 会重置中断标记，这里直接模拟运行中收到中断
    monkeypatch.setattr(worker, "isInterruptionRequested", lambda: True)
    worker.run()

    assert processed == []


def test_ingest_worker_processes_normally_without_interruption():
    processed: list[str] = []

    worker = IngestWorker(
        file_paths=["a.txt", "b.txt"],
        ingest_fn=lambda path: processed.append(path) or "doc",
    )
    worker.run()

    assert processed == ["a.txt", "b.txt"]
