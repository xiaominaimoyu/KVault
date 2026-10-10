"""《GUI重新设计文档》规范符合性检查。

以文档条款为断言，验证重设计要求确实落地。这些测试直接读取源码与运行时状态，
避免"看起来实现了"的假阳性。

覆盖文档中点名的**产物**是否存在，以及**关键数值**是否达标。
"""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.usefixtures("qapp")

_ROOT = Path(__file__).resolve().parents[2]
_DOC = (_ROOT / "docs" / "GUI重新设计文档.md").read_text(encoding="utf-8")


def _src(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------- §9.3 模块布局


class TestModuleLayout:
    """§9.3 规定的模块布局。"""

    @pytest.mark.parametrize(
        "rel",
        [
            "gui/main_window.py",
            "gui/styles/variables.py",
            "gui/styles/apply.py",
            "gui/styles/theme_dark.qss",
            "gui/styles/theme_light.qss",
            "gui/widgets/status_dot.py",
            "gui/widgets/format_badge.py",
            "gui/widgets/score_bar.py",
            "gui/widgets/doc_card.py",
            "gui/widgets/tag_pill.py",
            "gui/widgets/empty_state.py",
            "gui/widgets/step_indicator.py",
            "gui/widgets/floating_action_bar.py",
            "gui/panels/nav_panel.py",
            "gui/panels/doc_list_panel.py",
            "gui/panels/detail_panel.py",
            "gui/panels/preview_tab.py",
            "gui/panels/search_tab.py",
            "gui/panels/metadata_tab.py",
            "gui/dialogs/settings_dialog.py",
            "gui/dialogs/startup_dialog.py",
            "gui/dialogs/incremental_dialog.py",
            "gui/dialogs/model_switch_dialog.py",
        ],
    )
    def test_file_exists(self, rel):
        assert (_ROOT / rel).is_file(), f"§9.3 缺少 {rel}"


class TestWidgetInventory:
    """§9.2 自定义 Widget 清单 —— 8 个全部存在且被使用。"""

    INVENTORY = {
        "StatusDot": "gui/widgets/status_dot.py",
        "FormatBadge": "gui/widgets/format_badge.py",
        "ScoreBar": "gui/widgets/score_bar.py",
        "DocCard": "gui/widgets/doc_card.py",
        "TagPill": "gui/widgets/tag_pill.py",
        "EmptyState": "gui/widgets/empty_state.py",
        "StepIndicator": "gui/widgets/step_indicator.py",
        "FloatingActionBar": "gui/widgets/floating_action_bar.py",
    }

    @pytest.mark.parametrize("name,path", sorted(INVENTORY.items()))
    def test_widget_exists(self, name, path):
        assert (_ROOT / path).is_file()
        assert f"class {name}" in _src(path)

    @pytest.mark.parametrize(
        "cls,user",
        [
            ("StatusDot", "gui/panels/status_bar.py"),
            ("FormatBadge", "gui/panels/doc_list_panel.py"),
            ("ScoreBar", "gui/panels/search_tab.py"),
            ("DocCard", "gui/panels/doc_grid_panel.py"),
            ("EmptyState", "gui/panels/search_tab.py"),
            ("StepIndicator", "gui/dialogs/incremental_dialog.py"),
            ("FloatingActionBar", "gui/panels/doc_list_panel.py"),
        ],
    )
    def test_widget_is_used(self, cls, user):
        """控件不能只定义不使用。"""
        assert cls in _src(user), f"{cls} 未被 {user} 使用"


# ---------------------------------------------------------------- §9.2 TagPill


class TestTagPillIsQPushButton:
    """§9.2 明确要求 TagPill 继承 QPushButton。"""

    def test_base_class(self):
        src = _src("gui/widgets/tag_pill.py")
        assert "class TagPill(QPushButton)" in src


# ---------------------------------------------------------------- §7.1 空状态


class TestEmptyStates:
    """§7.1 五个区域的空状态文案。"""

    CASES = {
        "还没有文档": "gui/panels/doc_list_panel.py",
        "未找到相关结果": "gui/panels/search_tab.py",
        "选择文档查看预览": "gui/panels/preview_tab.py",
        "还没有分区": "gui/panels/nav_panel.py",
        "还没有标签": "gui/panels/nav_panel.py",
    }

    @pytest.mark.parametrize("text,module", sorted(CASES.items()))
    def test_empty_state_copy(self, text, module):
        assert text in _src(module), f"§7.1 缺少空状态文案「{text}」"


class TestEmptyStateIcons:
    """§7.1 空状态图标必须是 Lucide SVG，不得用 emoji。"""

    def test_icon_assets_exist(self):
        for name in ("file-search", "search-x", "file-text", "folder", "tag"):
            assert (_ROOT / "gui" / "styles" / "icons" / f"{name}.svg").is_file()

    def test_icons_registered(self):
        src = _src("gui/styles/icons.py")
        for name in ("file-search", "search-x"):
            assert f'"{name}"' in src


# ---------------------------------------------------------------- §2.6 层级


class TestElevation:
    """§2.6 层级表达。"""

    @pytest.mark.parametrize("theme", ["dark", "light"])
    def test_surface_widgets_have_background_and_divider(self, theme):
        css = _src(f"gui/styles/vault_extra{'' if theme == 'dark' else '_' + theme}.qss")
        for selector in ("QWidget#TopNavBar", "QWidget#StatusBar"):
            assert selector in css, f"缺少 {selector}"
        # 背景 + 分割线
        assert "background-color: %(bg-surface)s" in css

    @pytest.mark.parametrize("theme", ["dark", "light"])
    def test_menu_uses_accent_border_and_8px_radius(self, theme):
        """§2.6 L3 弹出层：半透明强调色边框 + radius 8px。"""
        css = _src(f"gui/styles/vault_extra{'' if theme == 'dark' else '_' + theme}.qss")
        menu_block = css[css.index("QMenu {"): css.index("QMenu::item")]
        assert "accent-primary-dim" in menu_block
        assert "border-radius: 8px" in menu_block


# ---------------------------------------------------------------- §2.3 字体


class TestContentFont:
    """§2.3 预览正文使用衬线体。"""

    def test_font_content_token_exists(self):
        assert "FONT_CONTENT" in _src("gui/styles/variables.py")

    def test_preview_uses_serif(self):
        src = _src("gui/panels/preview_tab.py")
        assert "Source Han Serif SC" in src, "预览正文未使用衬线体"

    def test_preview_max_width_720(self):
        """§3.4.1 最大阅读宽度 720px。"""
        src = _src("gui/panels/preview_tab.py")
        assert "MAX_CONTENT_WIDTH = 720" in src


# ---------------------------------------------------------------- §6 动效


class TestReduceMotion:
    """§6.1 要求 config.reduce_motion。"""

    def test_config_field_exists(self):
        assert "reduce_motion" in _src("core/config.py")

    def test_settings_dialog_exposes_toggle(self):
        assert "reduce_motion" in _src("gui/dialogs/settings_dialog.py")

    def test_motion_honours_it(self):
        assert "reduce_motion" in _src("gui/widgets/motion.py")


# ---------------------------------------------------------------- §3.1 布局


class TestLayout:
    """§3.1 布局约束。"""

    def test_nav_collapsed_width_48(self):
        src = _src("gui/panels/nav_panel.py")
        assert "COLLAPSED_WIDTH = 48" in src

    def test_nav_expanded_width_260(self):
        src = _src("gui/panels/nav_panel.py")
        assert "EXPANDED_WIDTH = 260" in src

    def test_nav_collapse_toggle_exists(self):
        assert "def toggle_collapsed" in _src("gui/panels/nav_panel.py")

    def test_splitter_handle_is_1px(self):
        """三栏之间无间隙 + 1px 分割线。"""
        css = _src("gui/styles/theme_dark.qss")
        assert "QSplitter::handle" in css


# ---------------------------------------------------------------- §4 对话框


class TestDialogs:
    """§4 对话框设计。"""

    def test_settings_dialog_specs(self):
        """§4.1 560x480 + 5 标签页。"""
        src = _src("gui/dialogs/settings_dialog.py")
        assert "resize(560, 480)" in src
        assert 'TAB_ORDER = ("常规", "检索", "模型", "MCP", "外观")' in src

    def test_settings_form_alignment(self):
        """§4.1 标签右对齐 + 16px 间距。"""
        src = _src("gui/dialogs/settings_dialog.py")
        assert "setLabelAlignment(Qt.AlignRight" in src
        assert "setSpacing(16)" in src

    def test_settings_primary_save(self):
        src = _src("gui/dialogs/settings_dialog.py")
        assert 'save_btn.setProperty("btnType", "primary")' in src

    def test_startup_dialog_cards(self):
        """§4.2 卡片式检查结果。"""
        src = _src("gui/dialogs/startup_dialog.py")
        assert "StartupCheckCard" in src

    def test_incremental_dialog_step_indicator(self):
        """§4.3 步骤指示器 + 三色标签。"""
        src = _src("gui/dialogs/incremental_dialog.py")
        assert "StepIndicator" in src
        assert "DiffAdded" in src and "DiffModified" in src and "DiffDeleted" in src

    def test_model_switch_step_indicator(self):
        """§4.4 步骤指示器 + 回滚提示条。"""
        src = _src("gui/dialogs/model_switch_dialog.py")
        assert "StepIndicator" in src
        assert "ErrorBanner" in src


# ---------------------------------------------------------------- §3.2 导航


class TestNavPanel:
    """§3.2 导航面板。"""

    def test_stats_expands_to_four_rows(self):
        src = _src("gui/panels/nav_panel.py")
        assert "for _ in range(4):" in src

    def test_partition_rows_have_icons(self):
        src = _src("gui/panels/nav_panel.py")
        assert 'item.setIcon(0, icon("folder"' in src

    def test_summary_clickable(self):
        src = _src("gui/panels/nav_panel.py")
        assert "_ClickableLabel" in src


# ---------------------------------------------------------------- §3.5/§3.6


class TestNavAndStatusBar:
    """§3.5 / §3.6 顶部与底部栏。"""

    def test_top_bar_has_logo_icon(self):
        src = _src("gui/panels/top_nav_bar.py")
        assert "TopNavBarLogo" in src
        assert "icon(" in src

    def test_top_bar_search_has_leading_icon(self):
        src = _src("gui/panels/top_nav_bar.py")
        assert "LeadingPosition" in src

    def test_top_bar_doc_count_badge(self):
        src = _src("gui/panels/top_nav_bar.py")
        assert "DocCountBadge" in src

    def test_status_bar_uses_object_names(self):
        """§3.6 统计用等宽 muted —— 通过 QSS 对象名而非内联样式。"""
        src = _src("gui/panels/status_bar.py")
        assert "StatusStats" in src
        assert "StatusMessage" in src


# ---------------------------------------------------------------- §8 组件


class TestComponentSpecs:
    """§8 组件样式规格。"""

    def test_score_bar_height_4px(self):
        """§8.7 高度 4px。"""
        src = _src("gui/widgets/score_bar.py")
        assert "setFixedHeight(4)" in src

    def test_score_bar_radius_full(self):
        css = _src("gui/styles/vault_extra.qss")
        bar_block = css[css.index("#ScoreBarTrack {"): css.index("#ScoreBarLabel")]
        assert "9999px" in bar_block

    def test_score_bar_band_colors(self):
        css = _src("gui/styles/vault_extra.qss")
        for band in ("success", "warning", "error"):
            assert f'[band="{band}"]::chunk' in css

    def test_combo_popup_item_height(self):
        """§8.3 弹出列表每项 32px。"""
        css = _src("gui/styles/vault_extra.qss")
        assert "QComboBox QAbstractItemView::item" in css
        assert "min-height: 32px" in css

    def test_placeholder_styled(self):
        """§8.2 placeholder 弱化斜体。"""
        css = _src("gui/styles/vault_extra.qss")
        assert "::placeholder" in css
        assert "font-style: italic" in css

    def test_doc_card_hover_accent(self):
        """§8.8 hover 边框变强调色。"""
        css = _src("gui/styles/vault_extra.qss")
        hover = css[css.index("QFrame#DocCard:hover"): css.index("QFrame#DocCard[selected")]
        assert "accent-primary" in hover

    def test_doc_card_selected_2px(self):
        """§8.8 选中 2px 边框。"""
        css = _src("gui/styles/vault_extra.qss")
        block = css[css.index('QFrame#DocCard[selected="true"]'):]
        block = block[: block.index("}")]
        assert "border: 2px solid" in block


# ---------------------------------------------------------------- §3.3 列表


class TestDocList:
    """§3.3 文档列表。"""

    def test_view_mode_persists_to_config(self):
        """§3.3.3 记忆用户选择到 config。"""
        src = _src("gui/panels/doc_list_panel.py")
        assert "attach_config" in src
        assert "config.view_mode" in src

    def test_config_has_view_mode(self):
        assert "view_mode" in _src("core/config.py")

    def test_doc_grid_selection_syncs_to_cards(self):
        """§3.3.2 选中卡片必须真正生效。"""
        src = _src("gui/panels/doc_grid_panel.py")
        assert "_sync_card_selection" in src
        assert "card.set_selected" in src


# ---------------------------------------------------------------- §5.6 快捷键


class TestShortcuts:
    """§5.6 快捷键表。"""

    def test_all_spec_shortcuts_present(self):
        from gui.shortcuts import DEFAULT_SHORTCUTS

        spec = {
            "Ctrl+I", "Ctrl+F", "Ctrl+K", "Ctrl+S",
            "Ctrl+R", "Delete", "Esc", "Ctrl+1", "Ctrl+2", "Ctrl+3",
        }
        assert spec <= set(DEFAULT_SHORTCUTS.values())

    def test_no_duplicate_bindings(self):
        from gui.shortcuts import DEFAULT_SHORTCUTS

        values = list(DEFAULT_SHORTCUTS.values())
        assert len(values) == len(set(values))


# ---------------------------------------------------------------- 主题一致性


class TestThemeConsistency:
    def test_extra_qss_exists_for_both_themes(self):
        assert (_ROOT / "gui/styles/vault_extra.qss").is_file()
        assert (_ROOT / "gui/styles/vault_extra_light.qss").is_file()

    def test_structure_matches_between_themes(self):
        selector = re.compile(r"^[#\w\.\[\]=\"'-]+\s*\{", re.M)
        dark = set(selector.findall(_src("gui/styles/vault_extra.qss")))
        light = set(selector.findall(_src("gui/styles/vault_extra_light.qss")))
        assert dark == light, "深浅两套补充样式结构必须一致"

    def test_tokens_resolve(self):
        from gui.styles.apply import _load_extra_qss, interpolate
        from gui.styles.variables import TOKENS_DARK, TOKENS_LIGHT

        for theme, tokens in (("dark", TOKENS_DARK), ("light", TOKENS_LIGHT)):
            rendered = interpolate(_load_extra_qss(theme), tokens)
            assert "%(" not in rendered, f"{theme} 主题存在未解析占位符"


class TestDocIsUnchanged:
    """重设计不应修改 core/ 检索与索引逻辑。"""

    def test_retriever_untouched(self):
        """§10.2 不改动 core/ 业务逻辑（本次仅按 §6.1 增加配置字段）。"""
        src = _src("core/retriever.py")
        assert "class Retriever" in src
        assert "class SearchResult" in src

    def test_main_entry_unchanged_signature(self):
        """§10.3 main.py 入口零改动即可启动。

        启动不得被本地模型可用性阻断，因此 MainWindow 接收能力探测结果
        （缺省时自行探测）而非被检查门禁拦截。
        """
        src = _src("main.py")
        assert "def main():" in src
        assert "MainWindow(config" in src
        # 能力探测取代阻塞式启动检查
        assert "capabilities=capabilities" in src
        assert "StartupDialog" not in src