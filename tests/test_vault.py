"""core/vault.py 测试，重点覆盖路径穿越防护与唯一命名。"""

import os
from pathlib import Path

import pytest

from core.vault import (
    NoteExistsError,
    NoteNotFoundError,
    UnsafePathError,
    Vault,
    normalize_rel_path,
    sanitize_title,
)


@pytest.fixture
def vault(tmp_path):
    return Vault(tmp_path / "vault")


class TestNormalizeRelPath:
    def test_simple(self):
        assert normalize_rel_path("a/b.md") == "a/b.md"

    def test_backslash_converted(self):
        assert normalize_rel_path("a\\b.md") == "a/b.md"

    def test_strips_redundant_parts(self):
        assert normalize_rel_path("./a//b/./c.md") == "a/b/c.md"

    def test_strips_trailing_slash(self):
        assert normalize_rel_path("a/b/") == "a/b"

    def test_rejects_leading_slash_as_absolute(self):
        with pytest.raises(UnsafePathError):
            normalize_rel_path("/a/b.md")

    def test_resolves_inner_parent(self):
        assert normalize_rel_path("a/b/../c.md") == "a/c.md"

    def test_empty(self):
        assert normalize_rel_path("") == ""
        assert normalize_rel_path("   ") == ""

    def test_rejects_escape(self):
        with pytest.raises(UnsafePathError):
            normalize_rel_path("../outside.md")

    def test_rejects_absolute_drive(self):
        with pytest.raises(UnsafePathError):
            normalize_rel_path("C:/Windows/system.ini")

    def test_rejects_unc(self):
        with pytest.raises(UnsafePathError):
            normalize_rel_path("//server/share/file.md")

    def test_rejects_none(self):
        with pytest.raises(UnsafePathError):
            normalize_rel_path(None)


class TestSanitizeTitle:
    def test_keeps_chinese(self):
        assert sanitize_title("我的笔记") == "我的笔记"

    def test_removes_wiki_breaking_chars(self):
        assert sanitize_title("a[b]c#d^e|f") == "a b c d e f"

    def test_trims_dots_and_spaces(self):
        assert sanitize_title("  ..名字..  ") == "名字"

    def test_empty_becomes_placeholder(self):
        assert sanitize_title("") == "未命名笔记"
        assert sanitize_title("///") == "未命名笔记"

    def test_reserved_windows_name_escaped(self):
        assert sanitize_title("CON") == "_CON"

    def test_length_capped(self):
        assert len(sanitize_title("长" * 300)) <= 100

    def test_slash_becomes_space(self):
        assert "/" not in sanitize_title("a/b")


class TestPathSafety:
    def test_abspath_simple(self, vault):
        assert vault.abspath("a.md") == vault.root / "a.md"

    def test_abspath_nested(self, vault):
        assert vault.abspath("a/b/c.md").is_relative_to(vault.root)

    def test_abspath_rejects_traversal(self, vault):
        with pytest.raises(UnsafePathError):
            vault.abspath("../secret.txt")

    def test_abspath_rejects_deep_traversal(self, vault):
        with pytest.raises(UnsafePathError):
            vault.abspath("a/../../secret.txt")

    def test_abspath_rejects_absolute(self, vault):
        with pytest.raises(UnsafePathError):
            vault.abspath("/etc/passwd")

    def test_symlink_escape_rejected(self, vault, tmp_path):
        # vault 外建立一个真实目录，并让 vault 内某个路径指向它
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("机密", encoding="utf-8")

        link = vault.root / "escape"
        try:
            os.symlink(outside, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("当前环境不支持创建符号链接")

        with pytest.raises(UnsafePathError):
            vault.abspath("escape/secret.txt")

    def test_write_cannot_escape(self, vault):
        with pytest.raises(UnsafePathError):
            vault.write("../escaped.md", "内容")

    def test_delete_cannot_escape(self, vault, tmp_path):
        victim = tmp_path / "victim.md"
        victim.write_text("重要", encoding="utf-8")
        with pytest.raises(UnsafePathError):
            vault.delete("../victim.md")
        assert victim.exists()


class TestCRUD:
    def test_create_and_read(self, vault):
        rel = vault.create("我的笔记", content="# 标题\n正文")
        assert rel == "我的笔记.md"
        assert "# 标题" in vault.read(rel)

    def test_create_in_folder(self, vault):
        rel = vault.create("计划", folder="项目/2024", content="内容")
        assert rel == "项目/2024/计划.md"
        assert (vault.root / "项目" / "2024" / "计划.md").is_file()

    def test_create_dedupes_title(self, vault):
        first = vault.create("计划", content="1")
        second = vault.create("计划", content="2")
        assert first == "计划.md"
        assert second == "计划 1.md"
        assert vault.read(second) == "2"

    def test_create_dedupes_within_folder(self, vault):
        vault.create("计划", folder="项目", content="1")
        rel = vault.create("计划", folder="项目", content="2")
        assert rel == "项目/计划 1.md"

    def test_create_overwrite_true_raises_if_exists(self, vault):
        vault.create("笔记", content="1")
        with pytest.raises(NoteExistsError):
            vault.create("笔记", content="2", overwrite=True)

    def test_read_missing_raises(self, vault):
        with pytest.raises(NoteNotFoundError):
            vault.read("不存在.md")

    def test_write_creates_parents(self, vault):
        vault.write("深/层/路径.md", "内容")
        assert vault.read("深/层/路径.md") == "内容"

    def test_write_is_visible_as_file(self, vault):
        vault.write("a.md", "x")
        assert (vault.root / "a.md").is_file()

    def test_delete_removes_file(self, vault):
        vault.create("临时", content="x")
        vault.delete("临时.md")
        assert not vault.exists("临时.md")

    def test_delete_missing_is_silent(self, vault):
        vault.delete("从未存在.md")

    def test_delete_prunes_empty_dirs(self, vault):
        vault.create("笔记", folder="空目录/深层", content="x")
        vault.delete("空目录/深层/笔记.md")
        assert not (vault.root / "空目录").exists()

    def test_delete_keeps_non_empty_dirs(self, vault):
        vault.create("甲", folder="目录", content="x")
        vault.create("乙", folder="目录", content="y")
        vault.delete("目录/甲.md")
        assert (vault.root / "目录").exists()

    def test_exists(self, vault):
        vault.create("在", content="x")
        assert vault.exists("在.md")
        assert not vault.exists("不在.md")


class TestRenameAndMove:
    def test_rename_keeps_content(self, vault):
        vault.create("旧名", content="内容")
        rel = vault.rename("旧名.md", "新名")
        assert rel == "新名.md"
        assert vault.read("新名.md") == "内容"
        assert not vault.exists("旧名.md")

    def test_rename_to_existing_gets_suffix(self, vault):
        vault.create("甲", content="1")
        vault.create("乙", content="2")
        rel = vault.rename("乙.md", "甲")
        assert rel == "甲 1.md"
        assert vault.read("甲.md") == "1"
        assert vault.read("甲 1.md") == "2"

    def test_rename_and_move_folder(self, vault):
        vault.create("笔记", content="x")
        rel = vault.rename("笔记.md", "笔记", new_folder="归档")
        assert rel == "归档/笔记.md"
        assert not vault.exists("笔记.md")

    def test_rename_missing_raises(self, vault):
        with pytest.raises(NoteNotFoundError):
            vault.rename("没有.md", "新名")

    def test_move_keeps_name(self, vault):
        vault.create("笔记", content="x")
        rel = vault.move("笔记.md", "子目录")
        assert rel == "子目录/笔记.md"


class TestTraversal:
    def test_iter_paths_finds_nested(self, vault):
        vault.create("一", folder="a", content="1")
        vault.create("二", folder="a/b", content="2")
        vault.create("三", content="3")
        paths = vault.iter_paths()
        assert "a/一.md" in paths
        assert "a/b/二.md" in paths
        assert "三.md" in paths

    def test_iter_paths_skips_ignored_dirs(self, vault):
        vault.create("正常", content="1")
        (vault.root / ".obsidian").mkdir()
        (vault.root / ".obsidian" / "隐藏.md").write_text("x", encoding="utf-8")
        (vault.root / "node_modules").mkdir()
        (vault.root / "node_modules" / "包.md").write_text("x", encoding="utf-8")

        paths = vault.iter_paths()
        assert paths == ["正常.md"]

    def test_iter_paths_skips_non_markdown(self, vault):
        vault.create("笔记", content="1")
        (vault.root / "图片.png").write_bytes(b"x")
        assert vault.iter_paths() == ["笔记.md"]

    def test_iter_paths_skips_hidden_files(self, vault):
        (vault.root / ".secret.md").write_text("x", encoding="utf-8")
        assert vault.iter_paths() == []

    def test_list_notes_returns_metadata(self, vault):
        vault.create("笔记", content="内容")
        notes = vault.list_notes()
        assert len(notes) == 1
        assert notes[0].name == "笔记"
        assert notes[0].folder == ""
        assert notes[0].size > 0

    def test_note_folder_property(self, vault):
        vault.create("笔记", folder="a/b", content="x")
        note = vault.list_notes()[0]
        assert note.folder == "a/b"
        assert note.name == "笔记"

    def test_to_rel_roundtrip(self, vault):
        rel = vault.create("笔记", folder="目录", content="x")
        assert vault.to_rel(vault.abspath(rel)) == rel


class TestIndex:
    def test_reindex_lists_notes(self, vault):
        vault.create("甲", content="# 甲")
        vault.create("乙", content="# 乙")
        index = vault.reindex()
        assert len(index) == 2
        assert "甲.md" in index

    def test_index_uses_h1_as_title(self, vault):
        vault.create("文件名", content="# 真实标题\n正文")
        index = vault.reindex()
        assert index.get("文件名.md").title == "真实标题"

    def test_index_frontmatter_title_wins(self, vault):
        vault.create("文件名", content="---\ntitle: 属性标题\n---\n# H1 标题\n正文")
        index = vault.reindex()
        assert index.get("文件名.md").title == "属性标题"

    def test_index_falls_back_to_filename(self, vault):
        vault.create("文件名", content="没有标题的正文")
        index = vault.reindex()
        assert index.get("文件名.md").title == "文件名"

    def test_resolve_by_name(self, vault):
        vault.create("目标笔记", content="x")
        vault.reindex()
        assert vault.resolve_link("目标笔记") == "目标笔记.md"

    def test_resolve_by_path(self, vault):
        vault.create("笔记", folder="目录", content="x")
        vault.reindex()
        assert vault.resolve_link("目录/笔记") == "目录/笔记.md"

    def test_resolve_with_md_extension(self, vault):
        vault.create("笔记", content="x")
        vault.reindex()
        assert vault.resolve_link("笔记.md") == "笔记.md"

    def test_resolve_relative_to_source_folder(self, vault):
        vault.create("笔记", folder="目录A", content="x")
        vault.create("笔记", folder="目录B", content="y")
        vault.reindex()
        assert vault.resolve_link("笔记", from_path="目录A/其它.md") == "目录A/笔记.md"

    def test_resolve_by_alias(self, vault):
        vault.create("真实文件", content="---\naliases:\n  - 昵称\n---\n正文")
        vault.reindex()
        assert vault.resolve_link("昵称") == "真实文件.md"

    def test_resolve_case_insensitive(self, vault):
        vault.create("MyNote", content="x")
        vault.reindex()
        assert vault.resolve_link("mynote") == "MyNote.md"

    def test_resolve_unknown_returns_none(self, vault):
        vault.create("笔记", content="x")
        vault.reindex()
        assert vault.resolve_link("不存在的笔记") is None

    def test_resolve_empty_returns_none(self, vault):
        assert vault.resolve_link("") is None
        assert vault.resolve_link("   ") is None

    def test_resolve_prefers_shortest_path(self, vault):
        vault.create("同名", folder="深层/嵌套/目录", content="x")
        vault.create("同名", content="x")
        vault.reindex()
        assert vault.resolve_link("同名") == "同名.md"

    def test_index_supports_contains_and_paths(self, vault):
        vault.create("甲", content="x")
        index = vault.reindex()
        assert "甲.md" in index
        assert index.paths == ["甲.md"]
        assert index.get("不存在.md") is None


class TestUniqueCandidates:
    def test_matches_fragment(self, vault):
        vault.create("机器学习笔记", content="x")
        vault.create("深度学习", content="x")
        vault.reindex()
        assert vault.unique_candidates("学习") == ["机器学习笔记.md", "深度学习.md"]

    def test_empty_fragment_returns_empty(self, vault):
        vault.create("笔记", content="x")
        vault.reindex()
        assert vault.unique_candidates("") == []

    def test_respects_limit(self, vault):
        for i in range(10):
            vault.create(f"笔记{i}", content="x")
        vault.reindex()
        assert len(vault.unique_candidates("笔记", limit=3)) == 3

    def test_no_match_returns_empty(self, vault):
        vault.create("甲", content="x")
        vault.reindex()
        assert vault.unique_candidates("zzz") == []


class TestConcurrentSafety:
    def test_read_after_external_edit(self, vault):
        vault.create("笔记", content="原始")
        # 模拟用户用外部编辑器修改
        (vault.root / "笔记.md").write_text("外部修改", encoding="utf-8")
        assert vault.read("笔记.md") == "外部修改"

    def test_file_deleted_outside_is_detected(self, vault):
        vault.create("笔记", content="x")
        (vault.root / "笔记.md").unlink()
        assert not vault.exists("笔记.md")

    def test_vault_creates_root_on_init(self, tmp_path):
        target = tmp_path / "自动创建" / "vault"
        v = Vault(target)
        assert v.root.is_dir()