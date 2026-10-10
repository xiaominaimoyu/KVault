"""SettingsDialog 分类标签页化设置对话框测试。"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from gui.dialogs.settings_dialog import SettingsDialog


class _LlamaCppCfg:
    model_path = "D:/models/test.gguf"
    n_gpu_layers = 4
    n_ctx = 2048


class _HybridCfg:
    enabled = True


def _make_config(**overrides):
    config = SimpleNamespace(
        files_dir=Path("D:/vault/files"),
        embedding_backend="ollama",
        ollama_base_url="http://localhost:11434",
        embedding_model="nomic-embed-text",
        llama_cpp=_LlamaCppCfg(),
        chunk_size=800,
        chunk_overlap=100,
        top_k=5,
        similarity_threshold=0.3,
        mcp_enabled=True,
        hybrid_search=_HybridCfg(),
        theme="system",
        reduce_motion=False,
        view_mode="table",
        save_calls=[],
    )
    config.validate = lambda: []
    config.save = lambda: config.save_calls.append(True)
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


@pytest.fixture
def dialog() -> SettingsDialog:
    return SettingsDialog(_make_config())


def test_construction_has_five_tabs(dialog):
    """§4.1 规定五个标签页：常规 / 检索 / 模型 / MCP / 外观。"""
    labels = [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())]
    assert labels == ["常规", "检索", "模型", "MCP", "外观"]


def test_dialog_size_matches_spec(dialog):
    """§4.1 规定窗口 560 x 480。"""
    assert dialog.width() == 560
    assert dialog.height() == 480


def test_general_tab_contains_data_dir_and_toggles(dialog):
    assert dialog.data_dir.text() == str(Path("D:/vault"))
    assert dialog.hybrid_enabled.isChecked() is True


def test_mcp_and_appearance_split_into_own_tabs(dialog):
    """MCP 与外观应有独立标签页，而不是挤在常规页里。"""
    assert dialog.mcp_enabled.isChecked() is True
    assert dialog.theme_combo.currentData() in ("system", "dark", "light")


def test_reduce_motion_toggle_reflects_config(dialog):
    """§6.1 reduce_motion 开关。"""
    assert dialog.reduce_motion.isChecked() is not dialog.config.reduce_motion


def test_save_button_uses_primary_style(dialog):
    """§4.1 保存按钮使用主按钮样式。"""
    primary = [
        b for b in dialog.findChildren(type(dialog.mcp_enabled))
        if b.property("btnType") == "primary"
    ]
    assert primary, "应存在主按钮样式的保存按钮"


def test_chunk_hint_uses_warm_dim_bar(dialog):
    """§4.1 切分参数变更提示使用 accent-warm-dim 背景信息条。"""
    assert dialog.chunk_hint.objectName() == "SettingsHintBar"


def test_model_tab_populated_from_config(dialog):
    assert dialog.backend_combo.currentData() == "ollama"
    assert dialog.ollama_url.text() == "http://localhost:11434"
    assert dialog.model_name.text() == "nomic-embed-text"
    # 初始后端为 ollama → stack 显示第 0 页
    assert dialog.config_stack.currentIndex() == 0


def test_model_tab_llama_cpp_backend_shows_second_page():
    dialog = SettingsDialog(_make_config(embedding_backend="llama_cpp"))
    assert dialog.backend_combo.currentData() == "llama_cpp"
    assert dialog.config_stack.currentIndex() == 1
    assert dialog.gguf_path.text() == "D:/models/test.gguf"
    assert dialog.n_gpu_layers.value() == 4
    assert dialog.n_ctx.value() == 2048


def test_retrieval_tab_populated_from_config(dialog):
    assert dialog.chunk_size.value() == 800
    assert dialog.chunk_overlap.value() == 100
    assert dialog.top_k.value() == 5
    assert dialog.threshold.text() == "0.3"


def test_save_writes_values_back(dialog, monkeypatch):
    monkeypatch.setattr(
        "gui.dialogs.settings_dialog.QMessageBox.warning", lambda *a, **k: None
    )
    config = dialog.config
    dialog.ollama_url.setText("http://127.0.0.1:11434")
    dialog.model_name.setText("new-model")
    dialog.chunk_size.setValue(1000)
    dialog.top_k.setValue(8)
    dialog.threshold.setText("0.45")
    dialog.mcp_enabled.setChecked(False)

    dialog._on_save()

    assert config.ollama_base_url == "http://127.0.0.1:11434"
    assert config.embedding_model == "new-model"
    assert config.chunk_size == 1000
    assert config.top_k == 8
    assert config.similarity_threshold == 0.45
    assert config.mcp_enabled is False
    assert config.save_calls == [True]
    assert dialog.result() == SettingsDialog.Accepted


# ---- P9 主题设置 ----

def test_theme_combo_options():
    dialog = SettingsDialog(_make_config())
    data = [dialog.theme_combo.itemData(i) for i in range(dialog.theme_combo.count())]
    assert data == ["system", "dark", "light"]


def test_theme_combo_reflects_config():
    dialog = SettingsDialog(_make_config(theme="light"))
    assert dialog.theme_combo.currentData() == "light"


def test_save_writes_theme_back(monkeypatch):
    monkeypatch.setattr(
        "gui.dialogs.settings_dialog.QMessageBox.warning", lambda *a, **k: None
    )
    config = _make_config()
    dialog = SettingsDialog(config)
    light_idx = dialog.theme_combo.findData("light")
    dialog.theme_combo.setCurrentIndex(light_idx)

    dialog._on_save()

    assert config.theme == "light"


def test_save_rejects_invalid_threshold(dialog, monkeypatch):
    warnings = []
    monkeypatch.setattr(
        "gui.dialogs.settings_dialog.QMessageBox.warning",
        lambda *a, **k: warnings.append(a),
    )
    dialog.threshold.setText("abc")
    dialog._on_save()
    assert warnings, "应弹出阈值格式警告"
    assert dialog.config.save_calls == []
    assert dialog.result() != SettingsDialog.Accepted


def test_save_blocked_by_validation_errors(monkeypatch):
    config = _make_config()
    config.validate = lambda: ["top_k 超出范围"]
    dialog = SettingsDialog(config)
    warnings = []
    monkeypatch.setattr(
        "gui.dialogs.settings_dialog.QMessageBox.warning",
        lambda *a, **k: warnings.append(a),
    )
    dialog._on_save()
    assert warnings, "应弹出校验失败警告"
    assert config.save_calls == []


def test_mcp_toggle_updates_button_text(dialog):
    assert dialog.mcp_enabled.text() == "已启用"
    dialog.mcp_enabled.setChecked(False)
    assert dialog.mcp_enabled.text() == "已禁用"


def test_hybrid_toggle_updates_button_text(dialog):
    assert dialog.hybrid_enabled.text() == "已启用"
    dialog.hybrid_enabled.setChecked(False)
    assert dialog.hybrid_enabled.text() == "已禁用"


def test_model_manager_switch_button_hidden_without_parent():
    dialog = SettingsDialog(_make_config())
    assert not hasattr(dialog, "switch_model_btn")


def test_save_llama_cpp_values(monkeypatch):
    monkeypatch.setattr(
        "gui.dialogs.settings_dialog.QMessageBox.warning", lambda *a, **k: None
    )
    config = _make_config(embedding_backend="llama_cpp")
    dialog = SettingsDialog(config)
    dialog.gguf_path.setText("D:/models/other.gguf")
    dialog.n_gpu_layers.setValue(10)
    dialog.n_ctx.setValue(4096)

    dialog._on_save()

    assert config.llama_cpp.model_path == "D:/models/other.gguf"
    assert config.llama_cpp.n_gpu_layers == 10
    assert config.llama_cpp.n_ctx == 4096
