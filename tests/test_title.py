"""core/title.py 测试。"""

from core.title import (
    excerpt,
    headings,
    reading_time_minutes,
    slugify,
    title_from_content,
    word_count,
)


class TestTitleFromContent:
    def test_h1_title(self):
        assert title_from_content("# 我的标题\n\n正文") == "我的标题"

    def test_ignores_h2(self):
        assert title_from_content("## 二级标题\n正文", fallback="回退") == "回退"

    def test_h1_with_trailing_hashes(self):
        assert title_from_content("# 标题 ###\n正文") == "标题"

    def test_indented_h1_allowed(self):
        assert title_from_content("  # 缩进标题\n正文") == "缩进标题"

    def test_fallback_when_no_h1(self):
        assert title_from_content("只有正文", fallback="文件名") == "文件名"

    def test_empty_content(self):
        assert title_from_content("", fallback="文件名") == "文件名"

    def test_frontmatter_h1_preferred_over_frontmatter_title(self):
        # title_from_content 只看正文，属性标题由调用方先行读取
        text = "---\ntitle: 属性\n---\n# 正文标题\n正文"
        assert title_from_content(text) == "正文标题"

    def test_list_item_with_hash_not_a_title(self):
        assert title_from_content("- # 不是标题\n正文", fallback="回退") == "回退"

    def test_fenced_h1_ignored(self):
        text = "```\n# 代码里的标题\n```\n\n# 真标题"
        assert title_from_content(text) == "真标题"


class TestWordCount:
    def test_chinese_counted_per_char(self):
        assert word_count("你好世界") == 4

    def test_english_counted_per_word(self):
        assert word_count("hello world") == 2

    def test_mixed(self):
        assert word_count("hello 世界") == 3

    def test_markup_not_counted(self):
        assert word_count("# 标题") == 2

    def test_empty(self):
        assert word_count("") == 0

    def test_fenced_code_excluded(self):
        assert word_count("正文\n\n```\n一 二 三 四\n```") == 2


class TestReadingTime:
    def test_short_note_minimum_one(self):
        assert reading_time_minutes("短笔记") == 1

    def test_empty_is_zero(self):
        assert reading_time_minutes("") == 0

    def test_long_note_scales(self):
        assert reading_time_minutes("字" * 4000) >= 10


class TestExcerpt:
    def test_strips_markup(self):
        assert excerpt("# 标题\n\n**粗体**文本") == "标题 粗体文本"

    def test_resolves_wikilink_to_text(self):
        assert excerpt("见 [[目标笔记]] 内容") == "见 目标笔记 内容"

    def test_uses_alias_when_present(self):
        assert excerpt("见 [[目标|别名]]") == "见 别名"

    def test_truncates_long_text(self):
        result = excerpt("字" * 500, length=50)
        assert len(result) <= 50
        assert result.endswith("…")

    def test_empty(self):
        assert excerpt("") == ""


class TestHeadings:
    def test_extracts_levels(self):
        result = headings("# 一\n正文\n## 二\n### 三")
        assert result == [(1, "一"), (2, "二"), (3, "三")]

    def test_ignores_fenced_content(self):
        assert headings("# 真标题\n```\n# 假的\n```") == [(1, "真标题")]

    def test_empty(self):
        assert headings("") == []

    def test_no_headings(self):
        assert headings("只有正文") == []


class TestSlugify:
    def test_sanitizes(self):
        assert slugify("a/b:c") == "a b c"

    def test_keeps_chinese(self):
        assert slugify("中文标题") == "中文标题"