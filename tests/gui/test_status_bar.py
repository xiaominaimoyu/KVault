"""StatusBar 底部状态栏测试。"""

from gui.panels.status_bar import StatusBar


def test_status_bar_construction():
    bar = StatusBar(reduce_motion=True)
    assert bar.height() == 32
    assert bar.objectName() == "StatusBar"


def test_set_status():
    bar = StatusBar(reduce_motion=True)
    bar.set_status("就绪", "success")
    assert bar._status_label.text() == "就绪"
    assert bar._status_dot._status == "success"


def test_set_stats_summary():
    bar = StatusBar(reduce_motion=True)
    bar.set_stats_summary("12 文档 · 340 块")
    assert bar._stats_label.text() == "12 文档 · 340 块"


def test_set_progress():
    bar = StatusBar(reduce_motion=True)
    bar.show_progress(True)
    bar.set_progress(60, "正在索引")
    assert bar._progress_bar.value() == 60
    assert not bar._progress_bar.isHidden()
    assert bar._status_label.text() == "正在索引"


def test_show_progress_hide():
    bar = StatusBar(reduce_motion=True)
    bar.show_progress(False)
    assert bar._progress_bar.isHidden()


def test_set_ollama_status_connected():
    bar = StatusBar(reduce_motion=True)
    bar.set_ollama_status(True)
    assert bar._ollama_dot._status == "success"
    assert "✓" in bar._ollama_label.text()


def test_set_ollama_status_disconnected():
    bar = StatusBar(reduce_motion=True)
    bar.set_ollama_status(False)
    assert bar._ollama_dot._status == "error"
    assert "✗" in bar._ollama_label.text()


def test_show_message():
    bar = StatusBar(reduce_motion=True)
    bar.show_message("测试消息")
    assert bar._status_label.text() == "测试消息"