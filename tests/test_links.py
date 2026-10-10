"""core/links.py 测试。"""

from core.links import (
    NoteLink,
    extract_links,
    extract_tags,
    format_link,
    normalize_target,
    parse_link_target,
    tag_hierarchy,
)


class TestExtractLinks:
    def test_plain_link(self):
        links = extract_links("参见 [[目标笔记]] 了解更多")
        assert len(links) == 1
        assert links[0].target == "目标笔记"
        assert links[0].embed is False
        assert links[0].alias is None

    def test_link_with_alias(self):
        links = extract_links("见 [[笔记A|显示名]]")
        assert links[0].target == "笔记A"
        assert links[0].alias == "显示名"
        assert links[0].display == "显示名"

    def test_link_with_heading(self):
        links = extract_links("见 [[笔记A#某小节]]")
        assert links[0].target == "笔记A"
        assert links[0].heading == "某小节"
        assert links[0].anchor == "#某小节"

    def test_link_with_heading_and_alias(self):
        links = extract_links("[[笔记A#小节|别名]]")
        assert links[0].target == "笔记A"
        assert links[0].heading == "小节"
        assert links[0].alias == "别名"

    def test_embed_link(self):
        links = extract_links("![[嵌入的笔记]]")
        assert links[0].embed is True
        assert links[0].target == "嵌入的笔记"

    def test_multiple_links_in_order(self):
        links = extract_links("[[一]] 然后 [[二]] 最后 [[三]]")
        assert [link.target for link in links] == ["一", "二", "三"]
        assert links[0].start < links[1].start < links[2].start

    def test_offsets_point_to_original_text(self):
        text = "前缀 [[目标]] 后缀"
        links = extract_links(text)
        assert text[links[0].start : links[0].end] == "[[目标]]"

    def test_path_link_with_slash(self):
        links = extract_links("[[文件夹/子笔记]]")
        assert links[0].target == "文件夹/子笔记"

    def test_empty_target_ignored(self):
        assert extract_links("[[]]") == []
        assert extract_links("[[|别名]]") == []

    def test_link_inside_fenced_code_ignored(self):
        text = "```python\ncode = '[[不是链接]]'\n```"
        assert extract_links(text) == []

    def test_link_inside_inline_code_ignored(self):
        assert extract_links("使用 `[[不是链接]]` 语法") == []

    def test_link_inside_tilde_fence_ignored(self):
        assert extract_links("~~~\n[[不是链接]]\n~~~") == []

    def test_markdown_link_is_not_wikilink(self):
        assert extract_links("[文本](https://example.com)") == []

    def test_wikilink_after_markdown_link(self):
        links = extract_links("[文本](https://a.com) 与 [[真链接]]")
        assert [link.target for link in links] == ["真链接"]

    def test_underscore_fence_longer_than_closer(self):
        text = "````\n[[不是链接]]\n```\n[[也是]]\n````\n[[是链接]]"
        links = extract_links(text)
        assert [link.target for link in links] == ["是链接"]

    def test_no_brackets_returns_empty(self):
        assert extract_links("普通文本没有链接") == []
        assert extract_links("") == []

    def test_multiline_links_collected(self):
        text = "第一行 [[甲]]\n第二行 [[乙]]"
        assert [link.target for link in extract_links(text)] == ["甲", "乙"]


class TestExtractTags:
    def test_simple_tag(self):
        tags = extract_tags("这是 #项目 的笔记")
        assert [tag.name for tag in tags] == ["项目"]

    def test_nested_tag(self):
        tags = extract_tags("#a/b/c")
        assert tags[0].name == "a/b/c"
        assert tags[0].depth == 3
        assert tags[0].parent == "a/b"

    def test_top_level_tag_has_no_parent(self):
        assert extract_tags("#a")[0].parent is None

    def test_underscore_and_dash_allowed(self):
        tags = extract_tags("#my_tag-x")
        assert tags[0].name == "my_tag-x"

    def test_hash_prefix_stripped(self):
        assert extract_tags("#abc")[0].text == "#abc"

    def test_pure_number_is_issue_not_tag(self):
        assert extract_tags("见 #123") == []

    def test_number_with_letters_is_tag(self):
        assert extract_tags("#v2")[0].name == "v2"

    def test_atx_heading_not_a_tag(self):
        assert extract_tags("# 标题\n正文") == []

    def test_deep_heading_not_a_tag(self):
        assert extract_tags("### 三级标题") == []

    def test_tag_in_inline_code_ignored(self):
        assert extract_tags("`#不是标签`") == []

    def test_tag_in_fenced_code_ignored(self):
        assert extract_tags("```\n# 不是标签\n```") == []

    def test_tag_inside_wikilink_ignored(self):
        assert extract_tags("[[笔记#小节]]") == []

    def test_tag_in_markdown_url_ignored(self):
        assert extract_tags("[链接](https://a.com/page#section)") == []

    def test_word_before_hash_not_a_tag(self):
        assert extract_tags("abc#def") == []

    def test_tag_offsets_and_multiple(self):
        text = "前 #一 后 #二"
        tags = extract_tags(text)
        assert [t.name for t in tags] == ["一", "二"]
        assert text[tags[0].start : tags[0].end] == "#一"

    def test_trailing_slash_stripped(self):
        assert extract_tags("#a/")[0].name == "a"

    def test_no_hash_returns_empty(self):
        assert extract_tags("没有标签") == []
        assert extract_tags("") == []

    def test_tag_with_chinese_and_latin(self):
        assert extract_tags("#AI大模型")[0].name == "AI大模型"


class TestTagHierarchy:
    def test_expands_parents(self):
        result = tag_hierarchy(["a/b/c"])
        assert result == {"a": 1, "a/b": 1, "a/b/c": 1}

    def test_counts_parent_occurrences(self):
        result = tag_hierarchy(["a/b", "a/c", "a"])
        assert result == {"a": 3, "a/b": 1, "a/c": 1}

    def test_strips_hash_prefix(self):
        assert tag_hierarchy(["#x"]) == {"x": 1}

    def test_ignores_empty(self):
        assert tag_hierarchy(["", "  "]) == {}

    def test_empty_list(self):
        assert tag_hierarchy([]) == {}


class TestHelpers:
    def test_parse_link_target(self):
        assert parse_link_target("笔记#小节|别名") == ("笔记", "小节")

    def test_normalize_target_strips_md_and_slashes(self):
        assert normalize_target("/文件夹/笔记.md/") == "文件夹/笔记"
        assert normalize_target("笔记.md") == "笔记"
        assert normalize_target("笔记") == "笔记"

    def test_format_link_roundtrip(self):
        text = format_link("笔记", alias="别名", heading="小节")
        links = extract_links(text)
        assert links[0].target == "笔记"
        assert links[0].alias == "别名"
        assert links[0].heading == "小节"

    def test_format_link_minimal(self):
        assert format_link("笔记") == "[[笔记]]"