"""笔记编辑器组件。

- :mod:`gui.editor.markdown_editor` —— 带行号与自动保存的编辑器
- :mod:`gui.editor.markdown_highlighter` —— Markdown 语法高亮
- :mod:`gui.editor.wiki_completer` —— ``[[`` 链接补全
- :mod:`gui.editor.note_viewer` —— 阅读视图
- :mod:`gui.editor.link_panels` —— 反链 / 出链面板
- :mod:`gui.editor.graph_view` —— 知识图谱视图
- :mod:`gui.editor.quick_switcher` —— 快速切换与命令面板
"""

from gui.editor.link_panels import BacklinkPanel, OutgoingLinkPanel
from gui.editor.markdown_editor import MarkdownEditor
from gui.editor.markdown_highlighter import MarkdownHighlighter
from gui.editor.note_viewer import NoteViewer
from gui.editor.wiki_completer import WikiLinkCompleter

__all__ = [
    "BacklinkPanel",
    "MarkdownEditor",
    "MarkdownHighlighter",
    "NoteViewer",
    "OutgoingLinkPanel",
    "WikiLinkCompleter",
]