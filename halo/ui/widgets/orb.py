"""Le widget orbe : affiche la dernière frame de la simulation à ~30 fps.

La simulation (orb_physics) reste pure ; le widget gère le canvas Braille,
la rampe de couleurs (palette de l'app), le timer et la mesure de coût/frame.
"""

from __future__ import annotations

import os
import sys
from time import perf_counter

from rich.style import Style
from textual.strip import Strip
from textual.widget import Widget

from halo.ui.app_link import halo_app
from halo.ui.braille import BrailleCanvas, ColorRamp
from halo.ui.theme import no_color
from halo.ui.widgets.orb_physics import OrbMode, OrbPhysics


def braille_supported() -> bool:
    if os.environ.get("HALO_NO_BRAILLE"):
        return False
    # Textual remplace sys.stdout en cours d'exécution : on sonde le flux d'origine.
    stream = sys.__stdout__ or sys.stdout
    encoding = getattr(stream, "encoding", None) or ""
    return "utf" in encoding.lower()


class Orb(Widget):
    DEFAULT_CSS = """
    Orb { width: 100%; height: 100%; }
    """

    def __init__(self, mode: OrbMode = OrbMode.CALM, *, particles: int = 260) -> None:
        super().__init__()
        self.physics = OrbPhysics(count=particles)
        self.physics.set_mode(mode)
        self._canvas: BrailleCanvas | None = None
        self._ramp: ColorRamp | None = None
        self._strips: list[Strip] = []
        self._last_tick = perf_counter()
        self.last_frame_ms = 0.0

    # ── API pilotée par l'app ────────────────────────────────────────────────

    def set_level(self, level: float) -> None:
        self.physics.set_level(level)

    def set_mode(self, mode: OrbMode) -> None:
        if not halo_app(self).motion.enabled:
            mode = OrbMode.STATIC
        self.physics.set_mode(mode)

    # ── cycle de vie ─────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self._build_ramp()
        if halo_app(self).motion.enabled:
            self.set_interval(1 / 30, self._tick)
        else:
            self.physics.set_mode(OrbMode.STATIC)
            self._render_frame()

    def on_resize(self) -> None:
        self._canvas = None
        self._render_frame()

    def refresh_palette(self) -> None:
        self._build_ramp()
        self._render_frame()

    def rainbow_pulse(self, duration: float = 2.6) -> None:
        """Easter egg : l'orbe s'irise une fois, puis reprend sa robe violette."""
        self._ramp = ColorRamp(
            ["#ff5f56", "#ffbd2e", "#27c93f", "#2ea8ff", "#8b5cf6", "#f472b6"],
            monochrome=no_color(),
        )
        self.set_timer(duration, self._build_ramp)

    def _build_ramp(self) -> None:
        palette = halo_app(self).palette
        self._ramp = ColorRamp(
            [palette.accent_deep, palette.accent, palette.accent_soft],
            monochrome=no_color(),
        )

    # ── simulation + rendu ───────────────────────────────────────────────────

    def _tick(self) -> None:
        now = perf_counter()
        dt, self._last_tick = now - self._last_tick, now
        self.physics.step(dt)
        self._render_frame()

    def _render_frame(self) -> None:
        if self.size.width <= 0 or self.size.height <= 0 or self._ramp is None:
            return
        started = perf_counter()
        canvas = self._canvas
        if canvas is None or canvas.width != self.size.width or canvas.height != self.size.height:
            canvas = BrailleCanvas(
                self.size.width, self.size.height, use_braille=braille_supported()
            )
            self._canvas = canvas
        canvas.clear()
        frame = self.physics.frame(canvas.dot_width, canvas.dot_height)
        canvas.plot(frame.xs, frame.ys, frame.glow)
        self._strips = [
            Strip(canvas.row_segments(y, self._ramp), cell_length=canvas.width)
            for y in range(canvas.height)
        ]
        cost = (perf_counter() - started) * 1000.0
        self.last_frame_ms = 0.9 * self.last_frame_ms + 0.1 * cost if self.last_frame_ms else cost
        self.refresh()

    def render_line(self, y: int) -> Strip:
        if y < len(self._strips):
            return self._strips[y]
        return Strip.blank(self.size.width, Style())
