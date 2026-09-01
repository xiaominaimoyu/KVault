from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.document_parser import DocumentParser


def test_supported_formats_include_images():
    formats = DocumentParser().supported_formats()
    assert ".png" in formats
    assert ".jpg" in formats
    assert ".jpeg" in formats


def test_txt_not_affected_by_optional_deps(tmp_path: Path):
    path = tmp_path / "note.txt"
    path.write_text("plain text content", encoding="utf-8")
    parsed = DocumentParser().parse(str(path))
    assert "plain text content" in parsed.content
    assert parsed.metadata["source"] == str(path)


def test_md_not_affected_by_optional_deps(tmp_path: Path):
    path = tmp_path / "note.md"
    path.write_text("# heading\nbody", encoding="utf-8")
    parsed = DocumentParser().parse(str(path))
    assert "heading" in parsed.content


def test_pdf_fallback_when_pdfplumber_missing(tmp_path: Path):
    path = tmp_path / "doc.pdf"
    path.write_bytes(b"%PDF-1.4 dummy")

    fake_page = MagicMock()
    fake_page.get_text.return_value = "fallback text"
    fake_doc = MagicMock()
    fake_doc.__iter__ = lambda self: iter([fake_page])
    fake_doc.page_count = 1

    with patch("core.optional_deps.OptionalDepDetector.has_pdfplumber", return_value=False), \
         patch("fitz.open", return_value=MagicMock(__enter__=lambda s: fake_doc, __exit__=lambda s, *a: False)):
        parsed = DocumentParser().parse(str(path))
    assert "fallback text" in parsed.content
    assert parsed.metadata["pages"] == 1


def test_pdf_table_extraction_with_pdfplumber(tmp_path: Path):
    path = tmp_path / "doc.pdf"
    path.write_bytes(b"%PDF-1.4 dummy")

    fake_page = MagicMock()
    fake_page.extract_text.return_value = "page text"
    fake_page.extract_tables.return_value = [
        [["A", "B"], ["1", "2"]],
    ]
    fake_pdf = MagicMock()
    fake_pdf.pages = [fake_page]

    pdfplumber_mod = MagicMock()
    pdfplumber_mod.open = MagicMock(return_value=MagicMock(__enter__=lambda s: fake_pdf, __exit__=lambda s, *a: False))

    with patch("core.optional_deps.OptionalDepDetector.has_pdfplumber", return_value=True), \
         patch.dict("sys.modules", {"pdfplumber": pdfplumber_mod}):
        parsed = DocumentParser().parse(str(path))
    assert "page text" in parsed.content
    assert "[Table]" in parsed.content
    assert "A | B" in parsed.content
    assert "1 | 2" in parsed.content
    assert parsed.metadata["pages"] == 1


def test_image_skip_when_rapidocr_missing(tmp_path: Path):
    path = tmp_path / "img.png"
    path.write_bytes(b"\x89PNG fake")

    with patch("core.optional_deps.OptionalDepDetector.has_rapidocr", return_value=False):
        parsed = DocumentParser().parse(str(path))
    assert parsed.content == ""
    assert parsed.metadata["ocr"] == "skipped"


def test_image_ocr_with_rapidocr(tmp_path: Path):
    path = tmp_path / "img.png"
    path.write_bytes(b"\x89PNG fake")

    fake_engine = MagicMock()
    fake_engine.return_value = ([(None, "line one"), (None, "line two")], None)
    rapidocr_mod = MagicMock()
    rapidocr_mod.RapidOCR = MagicMock(return_value=fake_engine)

    with patch("core.optional_deps.OptionalDepDetector.has_rapidocr", return_value=True), \
         patch.dict("sys.modules", {"rapidocr_onnxruntime": rapidocr_mod}):
        parsed = DocumentParser().parse(str(path))
    assert "line one" in parsed.content
    assert "line two" in parsed.content
    assert parsed.metadata["ocr"] == "rapidocr"


def test_image_ocr_empty_result(tmp_path: Path):
    path = tmp_path / "img.jpg"
    path.write_bytes(b"\xff\xd8 fake")

    fake_engine = MagicMock()
    fake_engine.return_value = (None, None)
    rapidocr_mod = MagicMock()
    rapidocr_mod.RapidOCR = MagicMock(return_value=fake_engine)

    with patch("core.optional_deps.OptionalDepDetector.has_rapidocr", return_value=True), \
         patch.dict("sys.modules", {"rapidocr_onnxruntime": rapidocr_mod}):
        parsed = DocumentParser().parse(str(path))
    assert parsed.content == ""
    assert parsed.metadata["ocr"] == "empty"


def test_pdf_table_extraction_exception_falls_back(tmp_path: Path):
    path = tmp_path / "doc.pdf"
    path.write_bytes(b"%PDF-1.4 dummy")

    fake_page = MagicMock()
    fake_page.get_text.return_value = "plain fallback"
    fake_doc = MagicMock()
    fake_doc.__iter__ = lambda self: iter([fake_page])
    fake_doc.page_count = 1

    pdfplumber_mod = MagicMock()
    pdfplumber_mod.open = MagicMock(side_effect=RuntimeError("corrupt pdf"))

    with patch("core.optional_deps.OptionalDepDetector.has_pdfplumber", return_value=True), \
         patch.dict("sys.modules", {"pdfplumber": pdfplumber_mod}), \
         patch("fitz.open", return_value=MagicMock(__enter__=lambda s: fake_doc, __exit__=lambda s, *a: False)):
        parsed = DocumentParser().parse(str(path))
    assert "plain fallback" in parsed.content