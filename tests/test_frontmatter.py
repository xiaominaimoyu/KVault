"""core/frontmatter.py 测试。"""

from core import frontmatter as fm


class TestParse:
    def test_no_frontmatter_returns_original(self):
        text = "# 标题\n\n正文"
        result = fm.parse(text)
        assert result.present is False
        assert result.data == {}
        assert result.body == text

    def test_simple_key_values(self):
        text = "---\ntitle: 我的笔记\ndraft: false\norder: 3\n---\n\n正文内容"
        result = fm.parse(text)
        assert result.present is True
        assert result.get("title") == "我的笔记"
        assert result.get("draft") is False
        assert result.get("order") == 3
        assert result.body == "正文内容"

    def test_inline_list(self):
        result = fm.parse('---\ntags: [机器学习, "深度学习"]\n---\nbody')
        assert result.tags == ["机器学习", "深度学习"]

    def test_block_list(self):
        result = fm.parse("---\ntags:\n  - a\n  - b\n---\nbody")
        assert result.get("tags") == ["a", "b"]
        assert result.tags == ["a", "b"]

    def test_nested_mapping(self):
        result = fm.parse("---\ncssclasses:\n  cls1: wide\n  cls2: dark\n---\nbody")
        assert result.get("cssclasses") == {"cls1": "wide", "cls2": "dark"}

    def test_tags_strip_hash_prefix(self):
        result = fm.parse("---\ntags:\n  - '#project'\n  - idea\n---\nbody")
        assert result.tags == ["project", "idea"]

    def test_tags_dedupe_preserving_order(self):
        result = fm.parse("---\ntags: [b, a, b]\n---\nbody")
        assert result.tags == ["b", "a"]

    def test_aliases(self):
        result = fm.parse('---\naliases:\n  - "别名一"\n  - 别名二\n---\nbody')
        assert result.aliases == ["别名一", "别名二"]

    def test_empty_list(self):
        result = fm.parse("---\ntags: []\naliases:\n---\nbody")
        assert result.tags == []
        assert result.get("aliases") is None

    def test_scalar_as_list(self):
        result = fm.parse("---\ntags: solo\n---\nbody")
        assert result.tags == ["solo"]

    def test_url_value_not_split(self):
        result = fm.parse("---\nsource: https://example.com/a\n---\nbody")
        assert result.get("source") == "https://example.com/a"

    def test_colon_in_quoted_value(self):
        result = fm.parse('---\ntitle: "时间: 12:30"\n---\nbody')
        assert result.get("title") == "时间: 12:30"

    def test_comment_lines_ignored(self):
        result = fm.parse("---\n# 这是注释\ntitle: 名字\n---\nbody")
        assert result.get("title") == "名字"

    def test_bom_tolerated(self):
        result = fm.parse("\ufeff---\ntitle: 名字\n---\nbody")
        assert result.present is True
        assert result.get("title") == "名字"

    def test_unclosed_fence_degrades(self):
        text = "---\ntitle: 未闭合\n\n正文"
        result = fm.parse(text)
        assert result.present is False
        assert result.body == text

    def test_empty_input(self):
        result = fm.parse("")
        assert result.present is False
        assert result.body == ""

    def test_body_offset_points_to_first_body_line(self):
        result = fm.parse("---\ntitle: a\n---\n\n第一行")
        assert result.body_offset == 4
        assert result.body == "第一行"

    def test_key_lookup_is_case_insensitive(self):
        result = fm.parse("---\nTitle: 大写\n---\nbody")
        assert result.get("title") == "大写"
        assert result.get("TITLE") == "大写"

    def test_set_replaces_case_insensitive_key(self):
        result = fm.parse("---\ntitle: 旧\n---\nbody")
        result.set("title", "新")
        assert result.data == {"title": "新"}

    def test_malformed_structure_does_not_raise(self):
        # 空键与游离列表项，不应抛异常
        result = fm.parse("---\n: 孤儿值\n- 游离项\n---\nbody")
        assert isinstance(result.data, dict)


class TestDump:
    def test_roundtrip_simple(self):
        data = {"title": "笔记", "tags": ["a", "b"], "draft": False}
        result = fm.parse(fm.dump(data, "正文"))
        assert result.present is True
        assert result.get("title") == "笔记"
        assert result.tags == ["a", "b"]
        assert result.get("draft") is False
        assert result.body == "正文"

    def test_dump_empty_data_returns_body(self):
        assert fm.dump({}, "正文") == "正文"
        assert fm.dump(None, "正文") == "正文"

    def test_dump_preserves_unicode_and_spaces(self):
        data = {"title": " 前后有空格 "}
        result = fm.parse(fm.dump(data, "body"))
        assert result.get("title") == " 前后有空格 "

    def test_dump_nested_mapping(self):
        data = {"cssclasses": {"a": "1", "b": "2"}}
        result = fm.parse(fm.dump(data, "body"))
        assert result.get("cssclasses") == {"a": "1", "b": "2"}

    def test_numeric_looking_string_stays_string(self):
        # 回归：未加引号的 "1" 回读后会变成整数，导致类型漂移
        result = fm.parse(fm.dump({"title": "1", "v": "3.14", "b": "true"}, "body"))
        assert result.get("title") == "1"
        assert result.get("v") == "3.14"
        assert result.get("b") == "true"

    def test_native_types_stay_typed(self):
        result = fm.parse(fm.dump({"n": 1, "f": 2.5, "b": True, "z": None}, "body"))
        assert result.get("n") == 1
        assert result.get("f") == 2.5
        assert result.get("b") is True
        assert result.get("z") is None

    def test_dump_escapes_colon_value(self):
        result = fm.parse(fm.dump({"title": "a: b"}, "body"))
        assert result.get("title") == "a: b"

    def test_dump_block_list_roundtrip(self):
        data = {"aliases": ["x", "y"], "nested": [{"k": "v"}, {"k2": "v2"}]}
        result = fm.parse(fm.dump(data, "body"))
        assert result.aliases == ["x", "y"]
        assert result.get("nested") == [{"k": "v"}, {"k2": "v2"}]

    def test_dump_empty_body(self):
        out = fm.dump({"title": "只有属性"}, "")
        assert out.startswith("---\n")
        assert out.endswith("---\n")


class TestHelpers:
    def test_update_preserves_other_keys_and_body(self):
        text = fm.dump({"title": "旧", "keep": "值"}, "正文")
        updated = fm.update(text, {"title": "新"})
        result = fm.parse(updated)
        assert result.get("title") == "新"
        assert result.get("keep") == "值"
        assert result.body == "正文"

    def test_update_none_removes_key(self):
        text = fm.dump({"title": "旧"}, "正文")
        result = fm.parse(fm.update(text, {"title": None}))
        assert "title" not in result.data

    def test_ensure_tags_merges_and_dedupes(self):
        text = fm.dump({"tags": ["a"]}, "正文")
        result = fm.parse(fm.ensure_tags(text, ["b", "#a", "c"]))
        assert result.tags == ["a", "b", "c"]

    def test_ensure_tags_on_note_without_frontmatter(self):
        result = fm.parse(fm.ensure_tags("# 普通笔记", ["x"]))
        assert result.tags == ["x"]
        assert result.body == "# 普通笔记"