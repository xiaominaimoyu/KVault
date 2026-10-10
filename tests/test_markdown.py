"""core/markdown.py 渲染器测试，重点覆盖 HTML 注入防护。"""

from core.markdown import RenderOptions, render, render_document, safe_url


class TestSafeUrl:
    def test_allows_known_schemes(self):
        for url in ("http://a.com", "https://a.com", "mailto:a@b.com", "ftp://a.com"):
            assert safe_url(url) == url

    def test_allows_relative(self):
        assert safe_url("./a.md") == "./a.md"
        assert safe_url("a.md") == "a.md"
        assert safe_url("#锚点") == "#锚点"
        assert safe_url("/绝对/路径") == "/绝对/路径"

    def test_blocks_dangerous_schemes(self):
        for url in (
            "javascript:alert(1)",
            "JavaScript:alert(1)",
            "data:text/html,<script>",
            "vbscript:msgbox",
            "file:///etc/passwd",
        ):
            assert safe_url(url) is None

    def test_empty_and_none(self):
        assert safe_url("") is None
        assert safe_url(None) is None


class TestBlocks:
    def test_heading(self):
        assert "<h1" in render("# 标题")
        assert ">标题</h1>" in render("# 标题")

    def test_heading_levels(self):
        for level in range(1, 7):
            assert f"<h{level}" in render("#" * level + " 标题")

    def test_heading_offset(self):
        html = render("# 标题", RenderOptions(heading_offset=1))
        assert "<h2" in html

    def test_heading_anchor(self):
        assert 'id="我的-标题"' in render("# 我的 标题")

    def test_paragraph(self):
        assert "<p>文本</p>" in render("文本")

    def test_multiline_paragraph_joined(self):
        html = render("第一行\n第二行")
        assert "<p>第一行\n第二行</p>" in html

    def test_horizontal_rule(self):
        assert "<hr />" in render("---")

    def test_unordered_list(self):
        html = render("- 甲\n- 乙")
        assert "<ul>" in html and html.count("<li>") == 2

    def test_ordered_list(self):
        html = render("1. 甲\n2. 乙")
        assert "<ol>" in html and html.count("<li>") == 2

    def test_nested_list(self):
        html = render("- 外层\n  - 内层")
        assert html.count("<ul>") == 2

    def test_list_continuation_line(self):
        html = render("- 第一行\n  第二行")
        assert "第一行" in html and "第二行" in html

    def test_blockquote(self):
        html = render("> 引用内容")
        assert "<blockquote>" in html and "引用内容" in html

    def test_blockquote_with_list(self):
        html = render("> - 甲\n> - 乙")
        assert "<li>" in html

    def test_code_fence(self):
        html = render("```python\nprint(1)\n```")
        assert "<pre><code" in html and 'class="language-python"' in html
        assert "print(1)" in html

    def test_code_fence_escapes_html(self):
        html = render("```\n<script>alert(1)</script>\n```")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_unclosed_code_fence(self):
        html = render("```\n代码内容")
        assert "代码内容" in html

    def test_table(self):
        html = render("| 名称 | 值 |\n| --- | --- |\n| 甲 | 1 |")
        assert "<table>" in html and "<th" in html and "<td" in html

    def test_table_alignment(self):
        html = render("| a | b |\n| :-- | --: |\n| 1 | 2 |")
        assert "text-align:left" in html
        assert "text-align:right" in html

    def test_table_with_inline_markup(self):
        html = render("| a |\n| --- |\n| **粗** |")
        assert "<strong>" in html

    def test_block_id_captured(self):
        html = render("段落内容 ^abc123")
        # 块 ID 应进入 id 属性，且不再残留在可见正文中
        assert html == '<p id="^abc123">段落内容</p>'


class TestInline:
    def test_bold(self):
        assert "<strong>粗</strong>" in render("**粗**")

    def test_italic_star(self):
        assert "<em>斜</em>" in render("*斜*")

    def test_strikethrough(self):
        assert "<del>删</del>" in render("~~删~~")

    def test_inline_code(self):
        assert "<code>x</code>" in render("`x`")

    def test_inline_code_not_parsed(self):
        html = render("`**不是粗体**`")
        assert "<strong>" not in html
        assert "不是粗体" in html

    def test_multibyte_backtick_code(self):
        assert "<code>a`b</code>" in render("``a`b``")

    def test_markdown_link(self):
        html = render("[文本](https://example.com)")
        assert 'href="https://example.com"' in html
        assert ">文本</a>" in html

    def test_autolink(self):
        html = render("<https://example.com>")
        assert 'href="https://example.com"' in html

    def test_image(self):
        html = render("![说明](https://a.com/b.png)")
        assert "<img" in html and 'src="https://a.com/b.png"' in html

    def test_tag_rendered(self):
        html = render("标签 #项目")
        assert 'class="kv-tag"' in html and ">项目</span>" in html

    def test_tag_highlight_disabled(self):
        html = render("标签 #项目", RenderOptions(highlight_tags=False))
        assert "kv-tag" not in html
        assert "#项目" in html

    def test_heading_text_not_a_tag(self):
        html = render("# 标题")
        assert "kv-tag" not in html


class TestWikilinks:
    def test_unresolved_link_marked(self):
        html = render("见 [[目标]]")
        assert "kv-link-unresolved" in html
        assert "目标</a>" in html

    def test_resolved_link(self):
        html = render("见 [[目标]]", RenderOptions(resolve=lambda t, f=None: "目录/目标.md"))
        assert "kv-link-resolved" in html
        assert 'data-resolved="目录/目标.md"' in html

    def test_alias_display(self):
        assert ">别名</a>" in render("[[目标|别名]]")

    def test_heading_anchor_in_href(self):
        html = render("[[目标#小节]]")
        assert 'href="目标#小节"' in html

    def test_block_reference(self):
        html = render("[[目标#^blk]]")
        assert 'href="目标#^blk"' in html

    def test_embed_renders(self):
        html = render("![[嵌入]]")
        assert "kv-embed" in html

    def test_embed_resolved_style(self):
        html = render("![[嵌入]]", RenderOptions(resolve=lambda t, f=None: "嵌入.md"))
        assert "kv-embed-resolved" in html

    def test_embed_missing_dropped(self):
        html = render("![[缺失]]", RenderOptions(embed_missing="none"))
        assert "kv-embed" not in html

    def test_target_attribute_records_raw_target(self):
        html = render("[[原始目标]]")
        assert 'data-target="原始目标"' in html

    def test_resolver_single_arg_signature_supported(self):
        html = render("[[目标]]", RenderOptions(resolve=lambda t: "x.md"))
        assert "kv-link-resolved" in html

    def test_resolver_exception_degrades(self):
        def boom(target, from_path=None):
            raise RuntimeError("解析失败")

        html = render("[[目标]]", RenderOptions(resolve=boom))
        assert "kv-link-unresolved" in html

    def test_resolve_disabled(self):
        html = render("[[目标]]", RenderOptions(resolve=lambda t, f=None: "x.md", resolve_links=False))
        assert "kv-link-unresolved" in html


class TestSecurity:
    """笔记内容可由用户或 MCP 写入，渲染器必须阻止 HTML 注入。"""

    def test_script_tag_escaped(self):
        html = render("<script>alert(1)</script>")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_img_onerror_escaped(self):
        html = render('<img src=x onerror="alert(1)">')
        # 原始标签必须被转义，属性无法成为真正的 HTML 属性
        assert "<img" not in html
        assert "&lt;img" in html
        assert 'onerror="' not in html

    def test_attribute_breakout_in_link(self):
        html = render('[文本](https://a.com" onmouseover="alert(1))')
        assert 'onmouseover="' not in html
        assert "&quot;" in html

    def test_javascript_url_not_clickable(self):
        html = render("[点我](javascript:alert(1))")
        assert "javascript:" not in html
        assert "<a " not in html
        assert "点我" in html

    def test_data_url_not_clickable(self):
        html = render("[点我](data:text/html;base64,PHN2Zz4=)")
        assert "data:text/html" not in html

    def test_vbscript_url_not_clickable(self):
        html = render("[点我](vbscript:msgbox(1))")
        assert "vbscript:" not in html

    def test_mailto_allowed(self):
        assert 'href="mailto:a@b.com"' in render("[邮件](mailto:a@b.com)")

    def test_relative_link_allowed(self):
        assert 'href="./其他笔记.md"' in render("[其他](./其他笔记.md)")

    def test_fragment_link_allowed(self):
        assert 'href="#小节"' in render("[小节](#小节)")

    def test_html_in_wikilink_target_escaped(self):
        html = render('[[<script>x</script>]]')
        assert "<script>" not in html

    def test_raw_html_in_heading_escaped(self):
        html = render("# <img src=x onerror=alert(1)>")
        assert "<img" not in html
        assert "&lt;img" in html

    def test_html_in_table_cell_escaped(self):
        html = render("| a |\n| --- |\n| <script>x</script> |")
        assert "<script>" not in html

    def test_html_in_blockquote_escaped(self):
        html = render("> <script>x</script>")
        assert "<script>" not in html

    def test_frontmatter_not_rendered(self):
        html = render("---\ntitle: 标题\n---\n正文")
        assert "title:" not in html
        assert "正文" in html


class TestRenderDocument:
    def test_produces_full_document(self):
        out = render_document("# 标题", title="笔记")
        assert out.startswith("<!DOCTYPE html>")
        assert "<title>笔记</title>" in out
        assert "<style>" in out

    def test_title_escaped(self):
        out = render_document("# x", title="<script>")
        assert "<title>&lt;script&gt;</title>" in out

    def test_extra_css_appended(self):
        out = render_document("x", options=RenderOptions(extra_css=".a{}"))
        assert ".a{}" in out

    def test_options_propagate_through_nesting(self):
        """嵌套结构（引用块中的列表）也必须沿用同一份选项。"""
        out = render("> - [[目标]]", RenderOptions(highlight_tags=False))
        assert "kv-link" in out
        html = render("> # 标签", RenderOptions(highlight_tags=False))
        assert "kv-tag" not in html

    def test_empty_input(self):
        assert render("") == ""

    def test_whitespace_only(self):
        assert render("   \n\n  ") == ""