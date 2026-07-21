from codex_usage_widget.config import ThemeName
from codex_usage_widget.theme import meter_color, theme_tokens


def test_theme_tokens_match_the_design_contract() -> None:
    # Given
    light = ThemeName.LIGHT
    dark = ThemeName.DARK

    # When
    light_tokens = theme_tokens(light)
    dark_tokens = theme_tokens(dark)

    # Then
    assert light_tokens.surface_primary == "#f4f3ee"
    assert light_tokens.text_primary == "#111827"
    assert dark_tokens.surface_primary == "#1e1e2e"
    assert dark_tokens.text_primary == "#cdd6f4"
    assert light_tokens.bar_width == 220
    assert dark_tokens.pet_size == 20
    assert dark_tokens.control_size == 20
    assert dark_tokens.control_icon_size == 14
    assert light_tokens.mini_icon_asset == "codex-color.png"
    assert dark_tokens.mini_icon_asset == "codex-color-dark.png"
    assert light_tokens.mini_background_key == "#fdfdfb"
    assert dark_tokens.mini_background_key == "#fdfdfb"
    assert dark_tokens.mini_battery_width == 48
    assert dark_tokens.mini_battery_height == 20
    assert dark_tokens.mini_group_pitch == 74
    assert dark_tokens.mini_height == 40
    # Codex-brand battery palette: shared fills, theme-specific label glyphs.
    assert light_tokens.mini_session_fill == "#7fd8bb"
    assert light_tokens.mini_weekly_fill == "#8ad3e6"
    assert light_tokens.mini_low_fill == "#f38ba8"
    assert light_tokens.mini_session_label == "#10a37f"
    assert light_tokens.mini_weekly_label == "#0e7490"
    assert dark_tokens.mini_session_label == "#7fd8bb"
    assert dark_tokens.mini_weekly_label == "#8ad3e6"


def test_meter_color_uses_the_semantic_boundary_colors() -> None:
    # Given
    percentages = (-10.0, 0.0, 50.0, 100.0, 120.0)

    # When
    colors = tuple(meter_color(value) for value in percentages)

    # Then
    assert colors == (
        "#a6e3a1",
        "#a6e3a1",
        "#f9e2af",
        "#f38ba8",
        "#f38ba8",
    )


def test_meter_color_interpolates_like_the_reference_widget() -> None:
    # Given
    percentages = (25.0, 75.0)

    # When
    colors = tuple(meter_color(value) for value in percentages)

    # Then
    assert colors == ("#d0e2a8", "#f6b6ac")
