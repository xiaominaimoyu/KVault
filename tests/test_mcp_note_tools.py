"""MCP 笔记工具测试。"""

import pytest

from core.note_store import NoteStore
from mcp_server import note_tools


@pytest.fixture
def store(tmp_path, monkeypatch):
    """注入一个隔离的 NoteStore。"""
    note_tools.reset_store_cache()
    instance = NoteStore(str(tmp_path / "kb.sqlite"), tmp_path / "vault")
    monkeypatch.setattr(note_tools, "_get_store", lambda workspace=None: instance)
    yield instance
    note_tools.reset_store_cache()


@pytest.fixture(autouse=True)
def readonly(monkeypatch):
    """默认处于只读模式。"""
    monkeypatch.delenv("KVAULT_ALLOW_WRITE", raising=False)


@pytest.fixture
def writable(monkeypatch):
    """开启写入模式。"""
    monkeypatch.setenv("KVAULT_ALLOW_WRITE", "1")


class TestWriteGate:
    def test_disabled_by_default(self):
        assert note_tools.write_allowed() is False

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
    def test_enabled_values(self, monkeypatch, value):
        monkeypatch.setenv("KVAULT_ALLOW_WRITE", value)
        assert note_tools.write_allowed() is True

    @pytest.mark.parametrize("value", ["0", "false", "", "no"])
    def test_disabled_values(self, monkeypatch, value):
        monkeypatch.setenv("KVAULT_ALLOW_WRITE", value)
        assert note_tools.write_allowed() is False

    def test_create_blocked_when_readonly(self, store):
        result = note_tools.create_note("标题")
        assert "error" in result
        assert result["write_allowed"] is False

    def test_append_blocked_when_readonly(self, store):
        path = store.create_note("笔记")
        result = note_tools.append_to_note(path, "内容")
        assert "error" in result

    def test_links_blocked_when_readonly(self, store):
        path = store.create_note("笔记")
        assert "error" in note_tools.update_note_links(path, ["其它"])


class TestListNotes:
    def test_empty_vault(self, store):
        result = note_tools.list_notes()
        assert result["notes"] == []
        assert result["count"] == 0

    def test_lists_notes(self, store):
        store.create_note("甲", content="内容甲")
        store.create_note("乙", content="内容乙")
        result = note_tools.list_notes()
        assert result["count"] == 2

    def test_includes_excerpt(self, store):
        store.create_note("甲", content="这是一段用于摘要的内容。")
        result = note_tools.list_notes()
        assert result["notes"][0]["excerpt"]

    def test_filter_by_folder(self, store):
        store.create_note("甲", folder="目录")
        store.create_note("乙")
        result = note_tools.list_notes(folder="目录")
        assert result["count"] == 1

    def test_filter_by_tag(self, store):
        store.create_note("甲", tags=["项目"])
        store.create_note("乙")
        result = note_tools.list_notes(tag="项目")
        assert result["count"] == 1

    def test_respects_limit(self, store):
        for i in range(5):
            store.create_note(f"笔记{i}")
        assert note_tools.list_notes(limit=2)["count"] == 2


class TestGetNote:
    def test_reads_by_path(self, store):
        path = store.create_note("笔记", content="# 内容")
        result = note_tools.get_note(path)
        assert "# 内容" in result["content"]
        assert result["path"] == path

    def test_reads_by_title(self, store):
        store.create_note("标题笔记", content="内容")
        assert note_tools.get_note("标题笔记")["title"] == "标题笔记"

    def test_missing_note_returns_error(self, store):
        assert "error" in note_tools.get_note("不存在的笔记")

    def test_includes_link_info(self, store):
        store.create_note("目标")
        source = store.create_note("来源", content="见 [[目标]]")
        result = note_tools.get_note(source)
        assert "目标" in result["outgoing_links"]

    def test_includes_backlinks(self, store):
        target = store.create_note("目标")
        store.create_note("来源", content="见 [[目标]]")
        result = note_tools.get_note(target)
        assert "来源.md" in result["backlinks"]


class TestSearchNotes:
    def test_finds_by_keyword(self, store):
        store.create_note("甲", content="这里提到了紫貂这种动物")
        store.create_note("乙", content="无关内容")
        result = note_tools.search_notes("紫貂")
        assert result["count"] == 1
        assert result["results"][0]["path"].startswith("甲")

    def test_requires_all_terms(self, store):
        store.create_note("甲", content="包含第一个词")
        store.create_note("乙", content="包含第一个词和第二个词")
        result = note_tools.search_notes("第一个词 第二个词")
        assert result["count"] == 1

    def test_empty_query_rejected(self, store):
        assert "error" in note_tools.search_notes("")

    def test_no_match(self, store):
        store.create_note("甲", content="内容")
        assert note_tools.search_notes("绝不存在")["count"] == 0

    def test_respects_limit(self, store):
        for i in range(5):
            store.create_note(f"笔记{i}", content="共同关键词")
        assert note_tools.search_notes("共同关键词", limit=2)["count"] == 2

    def test_ordered_by_score(self, store):
        store.create_note("少", content="关键词")
        store.create_note("多", content="关键词 关键词 关键词")
        result = note_tools.search_notes("关键词")
        assert result["results"][0]["title"] == "多"


class TestBacklinksAndTags:
    def test_backlinks(self, store):
        target = store.create_note("目标")
        store.create_note("甲", content="见 [[目标]]")
        store.create_note("乙", content="也见 [[目标]]")
        result = note_tools.get_backlinks(target)
        assert len(result["backlinks"]) == 2

    def test_broken_links_counted(self, store):
        source = store.create_note("来源", content="见 [[不存在]]")
        result = note_tools.get_backlinks(source)
        assert result["broken_count"] == 1

    def test_missing_note(self, store):
        assert "error" in note_tools.get_backlinks("不存在")

    def test_list_tags(self, store):
        store.create_note("甲", tags=["项目", "想法"])
        result = note_tools.list_tags()
        names = {item["tag"] for item in result["tags"]}
        assert {"项目", "想法"} <= names

    def test_tags_expand_hierarchy(self, store):
        store.create_note("甲", content="#项目/子项")
        result = note_tools.list_tags()
        names = {item["tag"] for item in result["tags"]}
        assert "项目" in names


class TestCreateNote:
    def test_creates(self, store, writable):
        result = note_tools.create_note("新笔记", content="内容")
        assert result["created"] is True
        assert store.get(result["path"]) is not None

    def test_creates_in_folder(self, store, writable):
        result = note_tools.create_note("新笔记", folder="目录")
        assert result["path"].startswith("目录/")

    def test_with_tags(self, store, writable):
        result = note_tools.create_note("带标签", tags=["项目"])
        assert "项目" in store.tags_for(result["path"])

    def test_empty_title_rejected(self, store, writable):
        assert "error" in note_tools.create_note("")

    def test_oversized_content_rejected(self, store, writable):
        assert "error" in note_tools.create_note("标题", content="x" * 20000)

    def test_dedupes_title(self, store, writable):
        first = note_tools.create_note("同名")
        second = note_tools.create_note("同名")
        assert first["path"] != second["path"]

    def test_no_write_when_blocked(self, store):
        note_tools.create_note("不应存在")
        assert store.list_notes() == []


class TestAppendToNote:
    def test_appends(self, store, writable):
        path = store.create_note("笔记", content="原始内容")
        result = note_tools.append_to_note(path, "追加内容")
        assert result["appended"] is True
        assert "追加内容" in store.read(path)

    def test_preserves_original(self, store, writable):
        path = store.create_note("笔记", content="原始内容")
        note_tools.append_to_note(path, "追加内容")
        content = store.read(path)
        assert "原始内容" in content
        assert content.index("原始内容") < content.index("追加内容")

    def test_missing_note(self, store, writable):
        assert "error" in note_tools.append_to_note("不存在", "内容")

    def test_empty_content_rejected(self, store, writable):
        path = store.create_note("笔记")
        assert "error" in note_tools.append_to_note(path, "   ")

    def test_index_updated_after_append(self, store, writable):
        path = store.create_note("笔记", content="原始")
        note_tools.append_to_note(path, "新增独特关键词紫貂")
        assert "紫貂" in store.tags_for(path) or "紫貂" in store.read(path)


class TestUpdateNoteLinks:
    def test_appends_link(self, store, writable):
        path = store.create_note("来源", content="原始")
        note_tools.update_note_links(path, ["目标"])
        assert "[[目标]]" in store.read(path)

    def test_multiple_links(self, store, writable):
        path = store.create_note("来源", content="原始")
        note_tools.update_note_links(path, ["甲", "乙"])
        content = store.read(path)
        assert "[[甲]]" in content and "[[乙]]" in content

    def test_duplicate_link_not_added_twice(self, store, writable):
        path = store.create_note("来源", content="原始")
        note_tools.update_note_links(path, ["目标"])
        note_tools.update_note_links(path, ["目标"])
        assert store.read(path).count("[[目标]]") == 1

    def test_removes_link(self, store, writable):
        path = store.create_note("来源", content="见 [[目标]]")
        note_tools.update_note_links(path, ["目标"], mode="remove")
        assert "[[目标]]" not in store.read(path)

    def test_invalid_mode_rejected(self, store, writable):
        path = store.create_note("来源")
        assert "error" in note_tools.update_note_links(path, ["x"], mode="替换")

    def test_empty_targets_rejected(self, store, writable):
        path = store.create_note("来源")
        assert "error" in note_tools.update_note_links(path, [])

    def test_link_resolution_after_create(self, store, writable):
        source = store.create_note("来源", content="原始")
        note_tools.update_note_links(source, ["目标"])
        store.create_note("目标")
        store.reindex_links()
        assert store.outgoing_links(source)[0].target_resolved == "目标.md"


class TestPathSafety:
    """笔记工具同样不能写到 vault 之外。"""

    def test_create_with_traversal_folder_rejected(self, store, writable):
        result = note_tools.create_note("恶意", folder="../../escape")
        # 要么被拒绝，要么被规整到 vault 内，绝不能写到 vault 外
        if "error" not in result:
            assert store.vault.abspath(result["path"]).is_relative_to(store.vault.root)

    def test_append_to_traversal_path_rejected(self, store, writable):
        store.create_note("笔记")
        result = note_tools.append_to_note("../outside.md", "内容")
        assert "error" in result


class TestNoStoreAvailable:
    def test_list_notes_handles_missing_store(self, monkeypatch):
        note_tools.reset_store_cache()
        monkeypatch.setattr(note_tools, "_get_store", lambda workspace=None: None)
        assert "error" in note_tools.list_notes()

    def test_get_note_handles_missing_store(self, monkeypatch):
        note_tools.reset_store_cache()
        monkeypatch.setattr(note_tools, "_get_store", lambda workspace=None: None)
        assert "error" in note_tools.get_note("x")

    def test_search_handles_missing_store(self, monkeypatch):
        note_tools.reset_store_cache()
        monkeypatch.setattr(note_tools, "_get_store", lambda workspace=None: None)
        assert "error" in note_tools.search_notes("x")