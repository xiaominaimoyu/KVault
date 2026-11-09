"""配色预设与 Token 派生测试。"""

from core.config import AppearanceConfig
from gui.styles.palettes import ACCENT_PRESETS, PRESET_ORDER, build_tokens
from gui.styles.variables import TOKENS_DARK, TOKENS_LIGHT


def test_preset_order_matches_presets():
    assert len(PRESET_ORDER) == 6
    assert set(PRESET_ORDER) == set(ACCENT_PRESETS)
    assert PRESET_ORDER[0] == "vault-teal"


def test_each_preset_has_dark_and_light_accent():
    for key, preset in ACCENT_PRESETS.items():
        assert preset["label"]
        assert preset["dark"].startswith("#") and len(preset["dark"]) == 7
        assert preset["light"].startswith("#") and len(preset["light"]) == 7


def test_default_tokens_keep_vault_accent():
    dark = build_tokens("dark", AppearanceConfig())
    light = build_tokens("light", AppearanceConfig())
    assert dark["accent-primary"] == TOKENS_DARK["accent-primary"]
    assert light["accent-primary"] == TOKENS_LIGHT["accent-primary"]


def test_default_tokens_match_variables():
    dark = build_tokens("dark")
    assert dark["bg-vault"] == TOKENS_DARK["bg-vault"]
    assert dark["fg-primary"] == TOKENS_DARK["fg-primary"]


def test_custom_accent_overrides_preset():
    appearance = AppearanceConfig(accent_custom="#FF0000")
    tokens = build_tokens("dark", appearance)
    assert tokens["accent-primary"] == "#FF0000"
    assert tokens["accent-rgb"] == "255, 0, 0"
    assert tokens["accent-fg"] == "#FFFFFF"
    # hover 比基色更亮，dim 比基色更暗
    assert tokens["accent-primary-hover"] != "#FF0000"
    assert tokens["accent-primary-dim"] != "#FF0000"


def test_bright_accent_uses_dark_text():
    tokens = build_tokens("dark", AppearanceConfig(accent_custom="#FFFF00"))
    assert tokens["accent-fg"] == "#0F1115"


def test_unknown_preset_falls_back_to_default():
    tokens = build_tokens("dark", AppearanceConfig(accent_preset="does-not-exist"))
    assert tokens["accent-primary"] == TOKENS_DARK["accent-primary"]


def test_invalid_custom_color_falls_back_to_preset():
    tokens = build_tokens("dark", AppearanceConfig(accent_custom="not-a-color"))
    assert tokens["accent-primary"] == TOKENS_DARK["accent-primary"]


def test_solid_background_uses_chosen_color():
    tokens = build_tokens(
        "dark",
        AppearanceConfig(background_mode="color", background_color="#1B2430"),
    )
    assert tokens["bg-vault"] == "#1B2430"
    assert tokens["bg-surface"] != tokens["bg-vault"]


def test_bright_solid_background_switches_to_light_text():
    tokens = build_tokens(
        "dark",
        AppearanceConfig(background_mode="color", background_color="#FAFAFA"),
    )
    assert tokens["bg-vault"] == "#FAFAFA"
    assert tokens["fg-primary"] == TOKENS_LIGHT["fg-primary"]


def test_image_background_makes_vault_transparent():
    tokens = build_tokens(
        "dark",
        AppearanceConfig(background_mode="image", background_image="x.png"),
    )
    assert tokens["bg-vault"] == "transparent"
    assert tokens["bg-surface"].startswith("rgba(")
    assert "0.88" in tokens["bg-surface"]


def test_all_tokens_are_strings_without_placeholders():
    for theme in ("dark", "light"):
        tokens = build_tokens(theme, AppearanceConfig())
        for key, value in tokens.items():
            assert isinstance(value, str), key
            assert "%(" not in value, key
