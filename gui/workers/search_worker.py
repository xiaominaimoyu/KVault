from PySide6.QtCore import QThread, Signal

from core.retriever import Retriever, SearchResult


class SearchWorker(QThread):
    results = Signal(list)
    error = Signal(str)

    def __init__(self, retriever: Retriever, query: str, top_k: int, filters: dict | None = None):
        super().__init__()
        self.retriever = retriever
        self.query = query
        self.top_k = top_k
        self.filters = filters

    def run(self):
        try:
            results: list[SearchResult] = self.retriever.search(
                self.query, top_k=self.top_k, filters=self.filters
            )
            self.results.emit(results)
        except Exception as e:
            self.error.emit(str(e))
