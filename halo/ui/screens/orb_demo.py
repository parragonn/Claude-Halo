"""Écran de mise au point de l'orbe (`halo --orb-demo`).

Pilote l'orbe sans micro : amplitude synthétique « façon parole » ou niveau
manuel, changement de mode, et coût par frame affiché en continu.
"""

from __future__ import annotations

import math
from time import perf_counter
from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Center, Middle
from textual.screen import Screen
from textual.widgets import Static

from halo.ui.app_link import halo_app
from halo.ui.widgets.orb import Orb
from halo.ui.widgets.orb_physics import OrbMode
from halo.ui.widgets.status_bar import StatusBar

_MODES = [OrbMode.LISTENING, OrbMode.THINKING, OrbMode.CALM, OrbMode.STATIC]
_MODE_LABELS = {
    OrbMode.LISTENING: "écoute (audio-réactif)",
    OrbMode.THINKING: "réflexion",
    OrbMode.CALM: "repos",
    OrbMode.STATIC: "statique",
}


class OrbInfo(Static):
    DEFAULT_CSS = "OrbInfo { width: auto; margin: 1 0 0 0; }"

    def render(self) -> Text:
        screen = self.screen
        assert isinstance(screen, OrbDemoScreen)
        palette = halo_app(self).palette
        orb = screen.orb
        text = Text(no_wrap=True)
        text.append("● ", style=palette.accent)
        text.append(_MODE_LABELS[orb.physics.mode], style="bold")
        text.append(
            f"   niveau {round(screen.level * 100):>3} % ({screen.source})",
            style=palette.text_secondary,
        )
        text.append(f"   {orb.last_frame_ms:.1f} ms/frame", style=palette.text_dim)
        return text


class OrbDemoScreen(Screen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("space", "toggle_auto", "auto/manuel", show=False),
        Binding("up", "level_up", "niveau +", show=False),
        Binding("down", "level_down", "niveau -", show=False),
        Binding("m", "cycle_mode", "mode", show=False),
        Binding("escape", "quit_demo", "quitter", show=False),
    ]

    DEFAULT_CSS = """
    OrbDemoScreen { align: center middle; }
    OrbDemoScreen #orb-box { width: 52; height: 22; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.orb = Orb(mode=OrbMode.LISTENING)
        self.auto = True
        self.level = 0.0
        self._mode_index = 0
        self._t0 = perf_counter()

    @property
    def source(self) -> str:
        return "auto" if self.auto else "manuel ↑↓"

    def compose(self) -> ComposeResult:
        with Middle():
            with Center(id="orb-box"):
                yield self.orb
            with Center():
                yield OrbInfo()
        yield StatusBar()

    def on_mount(self) -> None:
        self.set_interval(1 / 30, self._drive)
        self.set_interval(0.25, lambda: self.query_one(OrbInfo).refresh())
        self.query_one(StatusBar).set_hints(
            (
                ("espace", "auto/manuel"),
                ("↑ ↓", "niveau"),
                ("m", "mode"),
                ("échap", "quitter"),
            )
        )

    def _drive(self) -> None:
        if self.auto:
            t = perf_counter() - self._t0
            burst = max(0.0, math.sin(t * 2.1)) ** 1.6
            cadence = 0.55 + 0.45 * math.sin(t * 0.33)
            self.level = burst * cadence
        self.orb.set_level(self.level)

    def action_toggle_auto(self) -> None:
        self.auto = not self.auto

    def action_level_up(self) -> None:
        self.auto = False
        self.level = min(1.0, self.level + 0.1)

    def action_level_down(self) -> None:
        self.auto = False
        self.level = max(0.0, self.level - 0.1)

    def action_cycle_mode(self) -> None:
        self._mode_index = (self._mode_index + 1) % len(_MODES)
        self.orb.set_mode(_MODES[self._mode_index])

    def action_quit_demo(self) -> None:
        self.app.exit()
