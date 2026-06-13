"""Canvas Braille : résolution sous-cellule 2×4 points par caractère.

Substrat de rendu de l'orbe (U+2800–U+28FF). Repli propre sur des glyphes
points/blocs si le Braille n'est pas affichable. La rampe de couleurs mappe
une intensité 0..1 sur le dégradé violet (ou sur gras/dim en NO_COLOR).
"""

from __future__ import annotations

import numpy as np
from rich.segment import Segment
from rich.style import Style

# Bits braille par (ligne 0-3, colonne 0-1) dans une cellule.
_BIT = np.array([[0x01, 0x08], [0x02, 0x10], [0x04, 0x20], [0x40, 0x80]], dtype=np.uint16)

_POPCOUNT = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)

_FALLBACK_GLYPHS = " ··••●●●●"  # indexé par nombre de points (0..8)

# Style vide mais jamais None : le filtre d'opacité de Textual exige un Style.
_BLANK_STYLE = Style()


class ColorRamp:
    """Intensité 0..1 → style Rich, précalculé (cœur sombre → halo clair)."""

    def __init__(self, stops: list[str], steps: int = 24, monochrome: bool = False) -> None:
        self._styles: list[Style] = []
        if monochrome:
            for i in range(steps):
                t = i / (steps - 1)
                if t < 0.34:
                    self._styles.append(Style(dim=True))
                elif t < 0.72:
                    self._styles.append(Style())
                else:
                    self._styles.append(Style(bold=True))
            return
        rgb_stops = [self._hex_to_rgb(stop) for stop in stops]
        for i in range(steps):
            t = i / (steps - 1)
            position = t * (len(rgb_stops) - 1)
            low = min(int(position), len(rgb_stops) - 2)
            local = position - low
            a, b = rgb_stops[low], rgb_stops[low + 1]
            color = tuple(round(a[c] + (b[c] - a[c]) * local) for c in range(3))
            self._styles.append(Style(color="#{:02x}{:02x}{:02x}".format(*color)))

    @staticmethod
    def _hex_to_rgb(value: str) -> tuple[int, int, int]:
        value = value.lstrip("#")
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))

    def style(self, t: float) -> Style:
        index = int(max(0.0, min(1.0, t)) * (len(self._styles) - 1))
        return self._styles[index]


class BrailleCanvas:
    """Grille de cellules ; chaque cellule agrège bits braille + intensité max."""

    def __init__(self, width: int, height: int, use_braille: bool = True) -> None:
        self.width = max(1, width)
        self.height = max(1, height)
        self.use_braille = use_braille
        self.bits = np.zeros((self.height, self.width), dtype=np.uint16)
        self.value = np.zeros((self.height, self.width), dtype=np.float64)

    @property
    def dot_width(self) -> int:
        return self.width * 2

    @property
    def dot_height(self) -> int:
        return self.height * 4

    def clear(self) -> None:
        self.bits.fill(0)
        self.value.fill(0.0)

    def plot(self, xs: np.ndarray, ys: np.ndarray, values: np.ndarray) -> None:
        """Allume des points (coordonnées flottantes en espace « points »)."""
        xi = np.floor(xs).astype(np.int64)
        yi = np.floor(ys).astype(np.int64)
        keep = (xi >= 0) & (xi < self.dot_width) & (yi >= 0) & (yi < self.dot_height)
        if not keep.any():
            return
        xi, yi, vals = xi[keep], yi[keep], values[keep]
        cell_x, cell_y = xi >> 1, yi >> 2
        bits = _BIT[yi & 3, xi & 1]
        np.bitwise_or.at(self.bits, (cell_y, cell_x), bits)
        np.maximum.at(self.value, (cell_y, cell_x), vals)

    def row_segments(self, y: int, ramp: ColorRamp) -> list[Segment]:
        """Une ligne de cellules → segments Rich (runs de style fusionnés)."""
        if not 0 <= y < self.height:
            return [Segment(" " * self.width, _BLANK_STYLE)]
        bits_row = self.bits[y]
        value_row = self.value[y]
        segments: list[Segment] = []
        run_chars: list[str] = []
        run_style: Style = _BLANK_STYLE

        def flush() -> None:
            if run_chars:
                segments.append(Segment("".join(run_chars), run_style))

        for x in range(self.width):
            bits = int(bits_row[x])
            if bits == 0:
                char, style = " ", _BLANK_STYLE
            else:
                if self.use_braille:
                    char = chr(0x2800 + bits)
                else:
                    char = _FALLBACK_GLYPHS[int(_POPCOUNT[bits & 0xFF])]
                style = ramp.style(float(value_row[x]))
            if style is not run_style:
                flush()
                run_chars, run_style = [], style
            run_chars.append(char)
        flush()
        return segments or [Segment(" " * self.width, _BLANK_STYLE)]
