"""Barre de statut contextuelle : seulement les raccourcis pertinents à l'état."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from halo.ui.app_link import halo_app

type Hints = tuple[tuple[str, str], ...]


class StatusBar(Static):
    DEFAULT_CSS = """
    StatusBar { dock: bottom; height: 1; padding: 0 2; }
    """

    hints: reactive[Hints] = reactive(())

    def set_hints(self, hints: Hints) -> None:
        self.hints = hints

    def render(self) -> Text:
        palette = halo_app(self).palette
        text = Text(no_wrap=True, overflow="ellipsis")
        for index, (key, label) in enumerate(self.hints):
            if index:
                text.append("  ·  ", style=palette.text_dim)
            text.append(key, style="bold")
            text.append(f" {label}", style=palette.text_dim)
        return text
