
from pathlib import Path
import pytest
from core.document_parser import DocumentParser


def test_parse_txt(tmp_path: Path):
    path = tmp_path / "note.txt"
    path.write_text("hello world", encoding="utf-8")
    parsed = DocumentParser().parse(str(path))
    assert "hello world" in parsed.content
    assert parsed.metadata["source"] == str(path)


def test_unsupported_format(tmp_path: Path):
    path = tmp_path / "x.bin"
    path.write_bytes(b"abc")
    with pytest.raises(ValueError):
        DocumentParser().parse(str(path))


def test_supported_formats():
    formats = DocumentParser().supported_formats()
    assert ".pdf" in formats
    assert ".docx" in formats
