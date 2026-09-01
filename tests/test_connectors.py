from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.connectors.base import BaseConnector, ConnectorDoc
from core.connectors.local_dir import LocalDirConnector
from core.connectors.github import GithubConnector
from core.connectors.notion import NotionConnector
from core.connectors.feishu import FeishuConnector
from core.connectors.registry import ConnectorRegistry
from core.connectors.sync import ConnectorSync, SyncReport


@pytest.fixture
def local_dir(tmp_path: Path) -> Path:
    (tmp_path / "a.txt").write_text("content A", encoding="utf-8")
    (tmp_path / "b.md").write_text("# heading", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.txt").write_text("content C", encoding="utf-8")
    return tmp_path


def test_local_dir_list(local_dir: Path):
    conn = LocalDirConnector(str(local_dir))
    files = conn.list()
    assert "a.txt" in files
    assert "b.md" in files
    assert "sub/c.txt" in files


def test_local_dir_list_with_extensions(local_dir: Path):
    conn = LocalDirConnector(str(local_dir), extensions={".txt"})
    files = conn.list()
    assert "a.txt" in files
    assert "b.md" not in files
    assert "sub/c.txt" in files


def test_local_dir_fetch(local_dir: Path):
    conn = LocalDirConnector(str(local_dir))
    doc = conn.fetch("a.txt")
    assert doc.name == "a.txt"
    assert doc.content == b"content A"
    assert doc.ext == ".txt"


def test_local_dir_parse(local_dir: Path):
    conn = LocalDirConnector(str(local_dir))
    doc = conn.fetch("b.md")
    text = conn.parse(doc)
    assert "heading" in text


def test_local_dir_fetch_and_parse(local_dir: Path):
    conn = LocalDirConnector(str(local_dir))
    doc, text = conn.fetch_and_parse("sub/c.txt")
    assert "content C" in text
    assert doc.source_id == "sub/c.txt"


def test_local_dir_fetch_nonexistent(local_dir: Path):
    conn = LocalDirConnector(str(local_dir))
    with pytest.raises(FileNotFoundError):
        conn.fetch("nonexistent.txt")


def test_local_dir_no_network(local_dir: Path):
    conn = LocalDirConnector(str(local_dir))
    files = conn.list()
    for f in files:
        doc = conn.fetch(f)
        conn.parse(doc)


def test_notion_not_implemented():
    conn = NotionConnector()
    assert conn.list() == []
    doc = conn.fetch("page1")
    assert "未实现" in doc.metadata.get("warning", "")
    text = conn.parse(doc)
    assert "未实现" in text


def test_feishu_not_implemented():
    conn = FeishuConnector()
    assert conn.list() == []
    doc = conn.fetch("doc1")
    assert "未实现" in doc.metadata.get("warning", "")
    text = conn.parse(doc)
    assert "未实现" in text


def test_github_missing_requests():
    with patch("core.connectors.github._has_requests", return_value=False):
        conn = GithubConnector("owner/repo")
        assert conn.list() == []
        with pytest.raises(RuntimeError, match="requests 未安装"):
            conn.fetch("README.md")


def test_github_with_mock_requests():
    fake_resp = MagicMock()
    fake_resp.json.return_value = {
        "tree": [
            {"type": "blob", "path": "README.md"},
            {"type": "blob", "path": "docs/guide.md"},
            {"type": "tree", "path": "docs"},
        ]
    }
    fake_resp.raise_for_status = MagicMock()

    fake_raw_resp = MagicMock()
    fake_raw_resp.content = b"# README content"
    fake_raw_resp.raise_for_status = MagicMock()

    fake_requests = MagicMock()
    fake_requests.get = MagicMock(side_effect=[fake_resp, fake_raw_resp])

    with patch("core.connectors.github._has_requests", return_value=True), \
         patch.dict("sys.modules", {"requests": fake_requests}):
        conn = GithubConnector("owner/repo")
        files = conn.list()
        assert "README.md" in files
        assert "docs/guide.md" in files

        doc = conn.fetch("README.md")
        assert doc.content == b"# README content"


def test_registry_list_available():
    types = ConnectorRegistry.list_available()
    assert "local_dir" in types
    assert "github" in types
    assert "notion" in types
    assert "feishu" in types


def test_registry_create():
    conn = ConnectorRegistry.create("local_dir", dir_path=".")
    assert isinstance(conn, LocalDirConnector)


def test_registry_create_unknown():
    with pytest.raises(ValueError, match="未知的 connector 类型"):
        ConnectorRegistry.create("unknown_type")


def test_sync_local_dir(local_dir: Path):
    conn = LocalDirConnector(str(local_dir))
    sync = ConnectorSync(conn, "local_dir")
    report = sync.sync()
    assert report.total == 3
    assert report.synced == 3
    assert report.failed == 0


def test_sync_with_ingest_fn(local_dir: Path):
    conn = LocalDirConnector(str(local_dir))
    sync = ConnectorSync(conn, "local_dir")
    ingested = []

    def ingest_fn(source_id, name, content, metadata):
        ingested.append(name)
        return True

    report = sync.sync(ingest_fn=ingest_fn)
    assert report.synced == 3
    assert len(ingested) == 3


def test_sync_with_skip(local_dir: Path):
    conn = LocalDirConnector(str(local_dir))
    sync = ConnectorSync(conn, "local_dir")

    def ingest_fn(source_id, name, content, metadata):
        return False

    report = sync.sync(ingest_fn=ingest_fn)
    assert report.skipped == 3
    assert report.synced == 0


def test_sync_report_fields():
    report = SyncReport(connector_type="test")
    assert report.total == 0
    assert report.synced == 0
    assert report.skipped == 0
    assert report.failed == 0
    assert report.errors == []


def test_sync_list_failure():
    conn = MagicMock(spec=BaseConnector)
    conn.list.side_effect = RuntimeError("connection failed")
    sync = ConnectorSync(conn, "mock")
    report = sync.sync()
    assert report.failed == 0
    assert len(report.errors) == 1
    assert "list failed" in report.errors[0]


def test_connector_doc_ext():
    doc = ConnectorDoc(source_id="path/to/file.pdf", name="file.pdf", content=b"")
    assert doc.ext == ".pdf"