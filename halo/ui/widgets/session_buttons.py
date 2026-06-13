"""Boutons de session, ancrés sous l'orbe : Back to home / New session.

Jamais d'animation de déplacement : apparition et repositionnement par simple
fondu (spec §5). La sélection est pilotée par l'écran (tab puis flèches +
Entrée) — état visuel simple, pas de focus Textual.
"""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from halo.core.models import Command
from halo.ui.animation import DUR_BASE, EASING
from halo.ui.app_link import halo_app

_BUTTONS: tuple[tuple[Command, str], ...] = (
    (Command.BACK_HOME, "Back to home"),
    (Command.NEW_SESSION, "New session"),
)


class SessionButtons(Static):
    DEFAULT_CSS = """
    SessionButtons { height: 2; margin: 1 2 0 2; opacity: 0; display: none; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._index = 0
        self._visible = False
        self.active = False  # sélection au clavier en cours (tab)

    def render(self) -> Text:
        palette = halo_app(self).palette
        text = Text(no_wrap=True)
        for line, (_command, label) in enumerate(_BUTTONS):
            selected = self.active and line == self._index
            text.append("▸ " if selected else "  ", style=palette.accent if selected else "")
            text.append(
                label,
                style=f"bold {palette.accent}" if selected else palette.text_secondary,
            )
            if line + 1 < len(_BUTTONS):
                text.append("\n")
        return text

    # ── fondu (jamais de translation) ────────────────────────────────────────

    def reveal(self) -> None:
        if self._visible:
            return
        self._visible = True
        self.display = True
        if halo_app(self).motion.enabled:
            self.styles.opacity = 0.0
            self.styles.animate("opacity", 1.0, duration=DUR_BASE, easing=EASING)
        else:
            self.styles.opacity = 1.0

    def conceal(self) -> None:
        if not self._visible:
            return
        self._visible = False
        self.active = False
        self.styles.opacity = 0.0
        self.display = False

    # ── sélection pilotée par l'écran ────────────────────────────────────────

    def set_active(self, active: bool) -> None:
        self.active = active
        self.refresh()

    def move(self, delta: int) -> None:
        self._index = (self._index + delta) % len(_BUTTONS)
        self.refresh()

    def activate(self) -> None:
        command, _label = _BUTTONS[self._index]
        halo_app(self).dispatch_command(command)
