"""Palette Halo et thèmes Textual — accent unique posé sur les couleurs natives.

Le fond et le texte du terminal restent la base (thèmes `ansi=True`, valeurs
`ansi_default`). Halo ajoute UNE couleur d'accent (violet par défaut) et des
gris dérivés — idéalement calculés à partir des vraies couleurs du terminal
(sonde OSC), sinon des préréglages clair/sombre.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from textual.theme import Theme

from halo.ui.terminal_probe import RGB, TerminalColors

DEFAULT_ACCENT = "#8b5cf6"

ACCENT_PRESETS: tuple[tuple[str, str], ...] = (
    ("#8b5cf6", "Violet"),
    ("#6366f1", "Indigo"),
    ("#06b6d4", "Cyan"),
    ("#10b981", "Vert"),
    ("#f59e0b", "Ambre"),
    ("#f472b6", "Rose"),
)


def no_color() -> bool:
    """`NO_COLOR` : mode strictement monochrome (Textual retire les couleurs ;
    la hiérarchie repose sur gras/dim/italique/bordures)."""
    return bool(os.environ.get("NO_COLOR"))


def normalize_hex(value: str) -> str | None:
    value = value.strip().lstrip("#")
    if len(value) == 3 and all(c in "0123456789abcdefABCDEF" for c in value):
        value = "".join(c * 2 for c in value)
    if len(value) == 6 and all(c in "0123456789abcdefABCDEF" for c in value):
        return f"#{value.lower()}"
    return None


def hex_to_rgb(value: str) -> RGB:
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def rgb_to_hex(rgb: RGB) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def blend(start: RGB, end: RGB, amount: float) -> RGB:
    amount = max(0.0, min(1.0, amount))
    return (
        round(start[0] + (end[0] - start[0]) * amount),
        round(start[1] + (end[1] - start[1]) * amount),
        round(start[2] + (end[2] - start[2]) * amount),
    )


def lighten(hex_color: str, amount: float) -> str:
    return rgb_to_hex(blend(hex_to_rgb(hex_color), (255, 255, 255), amount))


def darken(hex_color: str, amount: float) -> str:
    return rgb_to_hex(blend(hex_to_rgb(hex_color), (0, 0, 0), amount))


@dataclass(frozen=True, slots=True)
class HaloPalette:
    """Tout ce que l'UI a le droit d'utiliser : 1 accent (3 nuances) + 3 gris."""

    dark: bool
    accent: str
    accent_soft: str
    accent_deep: str
    text_secondary: str
    text_dim: str
    border: str


_DARK_GRAYS = ("#a7a7b3", "#70707c", "#44444e")  # secondaire, dim, bordure
_LIGHT_GRAYS = ("#55555e", "#8d8d98", "#c9c9d1")


def derive_palette(colors: TerminalColors, accent_hex: str) -> HaloPalette:
    accent = normalize_hex(accent_hex) or DEFAULT_ACCENT
    if colors.dark:
        soft = lighten(accent, 0.35)
        deep = darken(accent, 0.45)
    else:
        soft = darken(accent, 0.12)
        deep = darken(accent, 0.35)

    background = colors.background
    foreground = colors.foreground
    if background is not None and foreground is None:
        foreground = (235, 235, 235) if colors.dark else (24, 24, 28)
    if background is not None and foreground is not None:
        secondary = rgb_to_hex(blend(background, foreground, 0.72))
        dim = rgb_to_hex(blend(background, foreground, 0.50))
        border = rgb_to_hex(blend(background, foreground, 0.26))
    else:
        secondary, dim, border = _DARK_GRAYS if colors.dark else _LIGHT_GRAYS

    return HaloPalette(
        dark=colors.dark,
        accent=accent,
        accent_soft=soft,
        accent_deep=deep,
        text_secondary=secondary,
        text_dim=dim,
        border=border,
    )


def build_theme(palette: HaloPalette) -> Theme:
    """Thème Textual « ansi » : fond/texte natifs + variables Halo pour le CSS."""
    return Theme(
        name="halo-dark" if palette.dark else "halo-light",
        ansi=True,
        primary=palette.accent,
        secondary=palette.accent_soft,
        accent=palette.accent,
        warning="#d97706",
        error="#f87171" if palette.dark else "#dc2626",
        success="#34d399" if palette.dark else "#059669",
        foreground="ansi_default",
        background="ansi_default",
        surface="ansi_default",
        panel="ansi_default",
        boost="ansi_default",
        dark=palette.dark,
        variables={
            "ansi-background": "ansi_default",
            "ansi-foreground": "ansi_default",
            "halo-accent": palette.accent,
            "halo-accent-soft": palette.accent_soft,
            "halo-accent-deep": palette.accent_deep,
            "halo-secondary": palette.text_secondary,
            "halo-dim": palette.text_dim,
            "halo-border": palette.border,
            "border-blurred": palette.border,
            "block-cursor-foreground": "ansi_default",
            "block-cursor-background": palette.accent,
            "input-cursor-background": palette.accent,
            "input-cursor-foreground": "ansi_default",
            "input-cursor-text-style": "none",
            "input-selection-background": palette.accent_deep,
            "input-selection-foreground": "ansi_default",
            "screen-selection-background": palette.accent_deep,
            "screen-selection-foreground": "ansi_default",
            "scrollbar": palette.border,
            "scrollbar-hover": palette.text_dim,
            "scrollbar-active": palette.accent,
            "scrollbar-background": "ansi_default",
            "scrollbar-corner-color": "ansi_default",
            "scrollbar-background-hover": "ansi_default",
            "scrollbar-background-active": "ansi_default",
        },
    )
