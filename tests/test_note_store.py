"""core/note_store.py 测试。"""

import pytest

from core.metadata_manager import MetadataManager
from core.note_store import NoteStore
from core.vault import Vault


@pytest.fixture
def store(tmp_path):
    """无 metadata 依赖的纯笔记库。"""
    return NoteStore(str(tmp_path / "kb.sqlite"), tmp_path / "vault")


@pytest.fixture
def indexed_store(tmp_path):
    """带 documents 索引的笔记库，验证与 RAG 管道打通。"""
    from core.vector_store import VectorStore

    chroma = tmp_path / "chroma"
    chroma.mkdir()
    metadata = MetadataManager(str(tmp_path / "kb.sqlite"), vector_store=VectorStore(str(chroma)))
    return NoteStore(str(tmp_path / "kb.sqlite"), tmp_path / "vault", metadata=metadata)


class TestCreate:
    def test_create_returns_path(self, store):
        rel = store.create_note("我的笔记")
        assert rel == "我的笔记.md"
        assert store.vault.exists(rel)

    def test_create_writes_h1_body(self, store):
        rel = store.create_note("标题")
        assert "# 标题" in store.read(rel)

    def test_create_in_folder(self, store):
        rel = store.create_note("计划", folder="项目")
        assert rel == "项目/计划.md"

    def test_create_dedupes(self, store):
        assert store.create_note("笔记") == "笔记.md"
        assert store.create_note("笔记") == "笔记 1.md"

    def test_create_with_tags(self, store):
        rel = store.create_note("笔记", tags=["项目", "#想法"])
        record = store.get(rel)
        assert set(store.tags_for(rel)) == {"项目", "想法"}
        assert record is not None

    def test_create_with_alias(self, store):
        rel = store.create_note("真实标题", alias="昵称")
        store.reindex_links()
        assert store.vault.resolve_link("昵称") == rel

    def test_create_indexes_immediately(self, store):
        rel = store.create_note("笔记")
        record = store.get(rel)
        assert record is not None
        assert record.title == "笔记"
        assert record.word_count > 0

    def test_create_accepts_explicit_content(self, store):
        rel = store.create_note("笔记", content="自定义正文")
        assert "自定义正文" in store.read(rel)


class TestSaveAndIndex:
    def test_save_updates_hash(self, store):
        rel = store.create_note("笔记")
        before = store.get(rel).content_hash
        store.save_note(rel, "完全不同的内容\n\n第二段")
        after = store.get(rel)
        assert after.content_hash != before

    def test_save_updates_word_count(self, store):
        rel = store.create_note("笔记")
        store.save_note(rel, "字" * 100)
        assert store.get(rel).word_count == 100

    def test_save_preserves_created_at(self, store):
        rel = store.create_note("笔记")
        created = store.get(rel).created_at
        store.save_note(rel, "新内容")
        assert store.get(rel).created_at == created

    def test_save_with_tags(self, store):
        rel = store.create_note("笔记")
        store.save_note(rel, "正文", tags=["新标签"])
        assert "新标签" in store.tags_for(rel)

    def test_save_with_title_renames_file(self, store):
        rel = store.create_note("旧名")
        record = store.save_note(rel, "# 新名\n正文", title="新名")
        assert record.path == "新名.md"
        assert store.get("新名.md") is not None
        assert store.get("旧名.md") is None

    def test_index_note_returns_record(self, store):
        store.vault.write("手动.md", "# 手动\n内容")
        record = store.index_note("手动.md", store.read("手动.md"))
        assert record.title == "手动"
        assert record.path == "手动.md"


class TestDelete:
    def test_delete_removes_file_and_index(self, store):
        rel = store.create_note("临时")
        store.delete_note(rel)
        assert not store.vault.exists(rel)
        assert store.get(rel) is None

    def test_delete_leaves_dangling_link_unresolved(self, store):
        """删除目标笔记后，入链应退回未解析状态（与 Obsidian 一致）。"""
        target = store.create_note("目标")
        source = store.create_note("来源", content="见 [[目标]]")
        store.delete_note(target)

        links = store.outgoing_links(source)
        assert len(links) == 1
        assert links[0].target_path == "目标"
        assert links[0].target_resolved is None
        assert store.backlinks("目标.md") == []

    def test_delete_keeps_other_notes(self, store):
        keep = store.create_note("保留")
        drop = store.create_note("删除")
        store.delete_note(drop)
        assert store.get(keep) is not None


class TestLinks:
    def test_outgoing_link_recorded(self, store):
        store.create_note("目标")
        source = store.create_note("来源", content="见 [[目标]] 结束")
        links = store.outgoing_links(source)
        assert len(links) == 1
        assert links[0].target_path == "目标"
        assert links[0].target_resolved == "目标.md"

    def test_backlink_recorded(self, store):
        store.create_note("目标")
        source = store.create_note("来源", content="见 [[目标]]")
        back = store.backlinks("目标.md")
        assert [record.source_path for record in back] == [source]

    def test_bidirectional_link(self, store):
        a = store.create_note("甲", content="指向 [[乙]]")
        b = store.create_note("乙", content="指向 [[甲]]")
        assert store.backlinks(a)[0].source_path == b
        assert store.backlinks(b)[0].source_path == a

    def test_broken_link_detected(self, store):
        source = store.create_note("来源", content="见 [[不存在]]")
        links = store.outgoing_links(source)
        assert links[0].target_resolved is None
        assert links[0].is_broken is True

    def test_broken_links_listing(self, store):
        store.create_note("甲", content="[[缺失笔记]]")
        broken = store.broken_links()
        assert len(broken) == 1
        assert broken[0].target_path == "缺失笔记"

    def test_embed_kind_recorded(self, store):
        store.create_note("目标")
        source = store.create_note("来源", content="![[目标]]")
        assert store.outgoing_links(source)[0].kind == "embed"

    def test_link_heading_and_alias_recorded(self, store):
        store.create_note("目标")
        source = store.create_note("来源", content="见 [[目标#小节|别名]]")
        link = store.outgoing_links(source)[0]
        assert link.heading == "小节"
        assert link.alias == "别名"

    def test_link_context_recorded(self, store):
        store.create_note("目标")
        source = store.create_note("来源", content="第一行\n第二行提到 [[目标]]\n第三行")
        link = store.outgoing_links(source)[0]
        assert "第二行" in link.context
        assert link.line_no == 2

    def test_links_in_code_block_ignored(self, store):
        store.create_note("目标")
        source = store.create_note("来源", content="```\n[[目标]]\n```")
        assert store.outgoing_links(source) == []

    def test_link_resolution_after_link_created_later(self, store):
        source = store.create_note("来源", content="见 [[稍后创建]]")
        assert store.outgoing_links(source)[0].target_resolved is None
        store.create_note("稍后创建")
        store.reindex_links()
        assert store.outgoing_links(source)[0].target_resolved == "稍后创建.md"

    def test_link_resolution_by_alias(self, store):
        store.create_note("真实名", alias="别名")
        store.reindex_links()
        source = store.create_note("来源", content="见 [[别名]]")
        assert store.outgoing_links(source)[0].target_resolved == "真实名.md"

    def test_renaming_updates_inbound_links(self, store):
        store.create_note("旧名")
        source = store.create_note("来源", content="见 [[旧名]]")
        store.rename_note("旧名.md", "新名")
        assert "新名" in store.read(source)
        assert store.backlinks("新名.md")[0].source_path == source

    def test_rename_then_resolves(self, store):
        store.create_note("旧名")
        store.create_note("来源", content="见 [[旧名]]")
        new_rel = store.rename_note("旧名.md", "新名")
        assert store.backlinks(new_rel)[0].source_path == "来源.md"

    def test_graph_adjacency(self, store):
        store.create_note("甲", content="[[乙]]")
        store.create_note("乙")
        store.create_note("丙")
        graph = store.linked_notes()
        assert graph["甲.md"] == ["乙.md"]
        assert "丙.md" not in graph

    def test_orphan_detection(self, store):
        store.create_note("孤立")
        store.create_note("甲", content="[[乙]]")
        store.create_note("乙")
        assert store.orphan_notes() == ["孤立.md"]

    def test_reindex_links_count(self, store):
        store.create_note("甲")
        store.create_note("乙")
        assert store.reindex_links() == 2


class TestTags:
    def test_inline_tag_indexed(self, store):
        rel = store.create_note("笔记", content="正文带 #行内标签")
        assert "行内标签" in store.tags_for(rel)

    def test_nested_tag_indexed(self, store):
        rel = store.create_note("笔记", content="标签 #项目/子项")
        assert "项目/子项" in store.tags_for(rel)

    def test_frontmatter_and_inline_merged(self, store):
        rel = store.create_note("笔记", tags=["属性标签"], content="还有 #行内标签")
        tags = set(store.tags_for(rel))
        assert {"属性标签", "行内标签"} <= tags

    def test_tag_removed_on_resave(self, store):
        rel = store.create_note("笔记", content="有 #旧标签")
        store.save_note(rel, "没有标签了")
        assert "旧标签" not in store.tags_for(rel)

    def test_list_tags_expands_hierarchy(self, store):
        store.create_note("甲", content="#项目/甲")
        store.create_note("乙", content="#项目/乙")
        counts = store.list_tags()
        assert counts["项目"] == 2
        assert counts["项目/甲"] == 1

    def test_notes_with_tag_includes_children(self, store):
        store.create_note("甲", content="#项目/甲")
        store.create_note("乙", content="#其它")
        assert store.notes_with_tag("项目") == ["甲.md"]

    def test_notes_with_tag_strips_hash(self, store):
        store.create_note("甲", content="#项目")
        assert store.notes_with_tag("#项目") == ["甲.md"]


class TestSync:
    def test_detects_new_file_on_disk(self, store):
        store.vault.write("外部创建.md", "# 外部\n内容")
        report = store.sync_all()
        assert report.added == ["外部创建.md"]
        assert store.get("外部创建.md") is not None

    def test_detects_modification(self, store):
        rel = store.create_note("笔记", content="原始")
        store.vault.write(rel, "修改后的内容")
        report = store.sync_all()
        assert report.updated == [rel]
        assert rel in report.changed

    def test_detects_deletion(self, store):
        rel = store.create_note("笔记")
        store.vault.delete(rel)
        report = store.sync_all()
        assert report.removed == [rel]
        assert store.get(rel) is None

    def test_unchanged_not_reindexed(self, store):
        store.create_note("笔记")
        report = store.sync_all()
        assert report.unchanged == 1
        assert report.changed == []

    def test_sync_multiple_notes(self, store):
        for i in range(3):
            store.create_note(f"笔记{i}", content=f"内容{i}")
        report = store.sync_all()
        assert report.unchanged == 3

    def test_sync_picks_up_nested_dir(self, store):
        store.vault.write("目录/深层.md", "# 深层")
        report = store.sync_all()
        assert "目录/深层.md" in report.added

    def test_sync_report_as_dict(self, store):
        store.create_note("笔记")
        data = store.sync_all().as_dict()
        assert data["unchanged"] == 1
        assert data["added"] == 0


class TestStats:
    def test_counts(self, store):
        store.create_note("甲", content="指向 [[乙]]")
        store.create_note("乙")
        store.create_note("丙", content="有 #标签 和 [[缺失]]")
        stats = store.stats()
        assert stats["notes"] == 3
        assert stats["links"] == 2
        assert stats["broken_links"] == 1
        assert stats["tags"] == 1

    def test_empty_store_stats(self, store):
        stats = store.stats()
        assert stats["notes"] == 0
        assert stats["words"] == 0


class TestListNotes:
    def test_list_all(self, store):
        store.create_note("甲")
        store.create_note("乙")
        assert {r.path for r in store.list_notes()} == {"甲.md", "乙.md"}

    def test_filter_by_folder(self, store):
        store.create_note("甲", folder="目录")
        store.create_note("乙")
        assert [r.path for r in store.list_notes(folder="目录")] == ["目录/甲.md"]

    def test_filter_by_keyword(self, store):
        store.create_note("机器学习")
        store.create_note("烹饪")
        assert [r.path for r in store.list_notes(keyword="学习")] == ["机器学习.md"]

    def test_note_record_derived_fields(self, store):
        rel = store.create_note("笔记", folder="目录")
        record = store.get(rel)
        assert record.name == "笔记"
        assert record.folder == "目录"


class TestDocumentBridge:
    """笔记必须能进入既有 RAG 检索管道。"""

    def test_note_registered_as_document(self, indexed_store):
        indexed_store.create_note("我的笔记", content="这是一段可检索的内容")
        docs = indexed_store.metadata.list_documents()
        assert any(d.file_name == "我的笔记.md" for d in docs)

    def test_note_uses_note_partition(self, indexed_store):
        indexed_store.create_note("笔记")
        names = {p["name"] for p in indexed_store.metadata.list_partitions()}
        assert "笔记" in names

    def test_note_has_document_id(self, indexed_store):
        rel = indexed_store.create_note("笔记")
        record = indexed_store.get(rel)
        assert record.document_id is not None

    def test_resave_updates_existing_document_not_duplicate(self, indexed_store):
        rel = indexed_store.create_note("笔记")
        doc_id = indexed_store.get(rel).document_id
        indexed_store.save_note(rel, "新的内容")
        assert indexed_store.get(rel).document_id == doc_id
        docs = [d for d in indexed_store.metadata.list_documents() if d.file_name == "笔记.md"]
        assert len(docs) == 1

    def test_delete_cleans_document_index(self, indexed_store):
        rel = indexed_store.create_note("临时笔记")
        indexed_store.delete_note(rel)
        assert not any(d.file_name == "临时笔记.md" for d in indexed_store.metadata.list_documents())

    def test_note_original_path_points_at_vault_file(self, indexed_store):
        rel = indexed_store.create_note("笔记")
        doc = next(d for d in indexed_store.metadata.list_documents() if d.file_name == "笔记.md")
        assert doc.stored_path == str(indexed_store.vault.abspath(rel))
        assert indexed_store.vault.abspath(rel).is_file()

    def test_fingerprint_recorded_for_incremental_update(self, indexed_store):
        rel = indexed_store.create_note("笔记")
        fingerprint = indexed_store.metadata.get_fingerprint(indexed_store.get(rel).document_id)
        assert fingerprint is not None
        assert fingerprint["content_hash"] == indexed_store.get(rel).content_hash


class TestVaultIntegration:
    def test_store_exposes_vault(self, store):
        assert isinstance(store.vault, Vault)

    def test_external_tool_edits_are_detected(self, store):
        rel = store.create_note("笔记")
        # 模拟用户在 Obsidian 里改文件
        store.vault.write(rel, "被外部修改的内容")
        report = store.sync_all()
        assert rel in report.updated

    def test_files_remain_plain_markdown(self, store):
        rel = store.create_note("笔记", tags=["标签"], content="# 正文\n[[其它]]")
        raw = store.vault.abspath(rel).read_text(encoding="utf-8")
        assert raw.startswith("---")
        assert "tags:" in raw
        assert "[[其它]]" in raw

    def test_deleting_index_preserves_files(self, store):
        rel = store.create_note("重要笔记", content="不可丢失的内容")
        # 仅移除索引，文件必须仍在
        store._forget(rel)
        assert store.get(rel) is None
        assert store.vault.read(rel) == "不可丢失的内容"