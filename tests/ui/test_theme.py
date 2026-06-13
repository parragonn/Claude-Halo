"""Parties pures du thème : parsing OSC, luminance, dérivation de palette."""

from __future__ import annotations

from halo.ui import theme
from halo.ui.terminal_probe import (
    TerminalColors,
    darkness_from_colorfgbg,
    is_dark,
    parse_osc_color,
    relative_luminance,
)


def test_parse_osc_color_16_bit() -> None:
    assert parse_osc_color("\x1b]11;rgb:ffff/0000/8080\x07") == (255, 0, 128)


def test_parse_osc_color_8_bit() -> None:
    assert parse_osc_color("rgb:1e/20/2c") == (30, 32, 44)


def test_parse_osc_color_hex() -> None:
    assert parse_osc_color("#1e202c") == (30, 32, 44)


def test_parse_osc_color_garbage() -> None:
    assert parse_osc_color("11;?") is None


def test_is_dark() -> None:
    assert is_dark((0, 0, 0))
    assert is_dark((30, 30, 46))
    assert not is_dark((255, 255, 255))
    assert not is_dark((250, 244, 237))


def test_darkness_from_colorfgbg() -> None:
    assert darkness_from_colorfgbg("15;0") is True
    assert darkness_from_colorfgbg("0;15") is False
    assert darkness_from_colorfgbg("12;default;0") is True
    assert darkness_from_colorfgbg("") is None
    assert darkness_from_colorfgbg("x;y") is None


def test_normalize_hex() -> None:
    assert theme.normalize_hex("8B5CF6") == "#8b5cf6"
    assert theme.normalize_hex("#abc") == "#aabbcc"
    assert theme.normalize_hex("pas une couleur") is None


def test_palette_presets_without_detected_rgb() -> None:
    palette = theme.derive_palette(TerminalColors(None, None, True), "#8B5CF6")
    assert palette.dark
    assert palette.accent == "#8b5cf6"
    assert palette.border == "#44444e"
    light = theme.derive_palette(TerminalColors(None, None, False), "#8B5CF6")
    assert light.border == "#c9c9d1"


def test_palette_blends_real_terminal_colors() -> None:
    background, foreground = (20, 20, 30), (200, 200, 210)
    palette = theme.derive_palette(TerminalColors(foreground, background, True), "#8B5CF6")
    assert palette.border == theme.rgb_to_hex(theme.blend(background, foreground, 0.26))
    assert palette.text_dim == theme.rgb_to_hex(theme.blend(background, foreground, 0.50))


def test_accent_ramp_direction() -> None:
    dark = theme.derive_palette(TerminalColors(None, None, True), "#8B5CF6")
    accent_lum = relative_luminance(theme.hex_to_rgb(dark.accent))
    assert relative_luminance(theme.hex_to_rgb(dark.accent_soft)) > accent_lum
    assert relative_luminance(theme.hex_to_rgb(dark.accent_deep)) < accent_lum


def test_invalid_accent_falls_back_to_violet() -> None:
    palette = theme.derive_palette(TerminalColors(None, None, True), "n'importe quoi")
    assert palette.accent == theme.DEFAULT_ACCENT.lower()


def test_build_theme_keeps_native_terminal_colors() -> None:
    palette = theme.derive_palette(TerminalColors(None, None, True), "#8B5CF6")
    textual_theme = theme.build_theme(palette)
    assert textual_theme.ansi is True
    assert textual_theme.name == "halo-dark"
    assert textual_theme.background == "ansi_default"
    assert textual_theme.variables["halo-accent"] == "#8b5cf6"
