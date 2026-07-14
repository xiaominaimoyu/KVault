from dataclasses import dataclass
from langchain_text_splitters import RecursiveCharacterTextSplitter


@dataclass
class Chunk:
    content: str
    metadata: dict


class KnowledgeTextSplitter:
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 100):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "。", "！", "？", " ", ""],
        )

    def split(self, content: str, doc_metadata: dict) -> list[Chunk]:
        if not content:
            return []
        pieces = self.splitter.split_text(content)
        total = len(pieces)
        return [
            Chunk(
                content=p,
                metadata={
                    **doc_metadata,
                    "chunk_index": i,
                    "total_chunks": total,
                },
            )
            for i, p in enumerate(pieces)
        ]
