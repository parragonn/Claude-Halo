"""Empaquetage des bits Braille, repli glyphes, rampe de couleurs."""

from __future__ import annotations

import numpy as np

from halo.ui.braille import BrailleCanvas, ColorRamp


def plot_one(canvas: BrailleCanvas, x: float, y: float, value: float = 1.0) -> None:
    canvas.plot(np.array([x]), np.array([y]), np.array([value]))


def test_single_dot_top_left() -> None:
    canvas = BrailleCanvas(2, 2)
    plot_one(canvas, 0.2, 0.2)
    assert canvas.bits[0, 0] == 0x01
    segments = canvas.row_segments(0, ColorRamp(["#000000", "#ffffff"]))
    assert segments[0].text.startswith(chr(0x2800 + 0x01))


def test_bottom_right_dot_of_cell() -> None:
    canvas = BrailleCanvas(2, 2)
    plot_one(canvas, 1.0, 3.0)
    assert canvas.bits[0, 0] == 0x80


def test_dots_in_same_cell_are_ored() -> None:
    canvas = BrailleCanvas(1, 1)
    plot_one(canvas, 0.0, 0.0)
    plot_one(canvas, 1.0, 3.0)
    assert canvas.bits[0, 0] == 0x81


def test_dot_coordinates_map_to_cells() -> None:
    canvas = BrailleCanvas(4, 4)
    plot_one(canvas, 5.0, 9.0)  # colonne 5 -> cellule 2 ; ligne 9 -> cellule 2
    assert canvas.bits[2, 2] != 0


def test_out_of_bounds_is_ignored() -> None:
    canvas = BrailleCanvas(2, 2)
    canvas.plot(np.array([-1.0, 99.0]), np.array([0.0, 0.0]), np.array([1.0, 1.0]))
    assert canvas.bits.sum() == 0


def test_value_keeps_maximum() -> None:
    canvas = BrailleCanvas(1, 1)
    plot_one(canvas, 0.0, 0.0, 0.3)
    plot_one(canvas, 1.0, 0.0, 0.9)
    assert canvas.value[0, 0] == 0.9


def test_glyph_fallback_by_density() -> None:
    canvas = BrailleCanvas(1, 1, use_braille=False)
    plot_one(canvas, 0.0, 0.0)
    light = canvas.row_segments(0, ColorRamp(["#000000", "#ffffff"]))[0].text
    for x in range(2):
        for y in range(4):
            plot_one(canvas, float(x), float(y))
    dense = canvas.row_segments(0, ColorRamp(["#000000", "#ffffff"]))[0].text
    assert light == "·"
    assert dense == "●"


def test_color_ramp_endpoints_and_clamp() -> None:
    ramp = ColorRamp(["#000000", "#ffffff"], steps=8)
    low = ramp.style(-1.0)
    high = ramp.style(2.0)
    assert low.color is not None and low.color.name == "#000000"
    assert high.color is not None and high.color.name == "#ffffff"


def test_monochrome_ramp_uses_weight_not_color() -> None:
    ramp = ColorRamp(["#000000", "#ffffff"], monochrome=True)
    assert ramp.style(0.0).dim
    assert ramp.style(1.0).bold
    assert ramp.style(1.0).color is None
