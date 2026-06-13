"""Écran IDLE/CONFIG : en-tête discret, tableau de bord, barre de statut."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Static

from halo import __version__
from halo.ui.app_link import halo_app
from halo.ui.sections import build_sections
from halo.ui.widgets.config_panel import ConfigPanel
from halo.ui.widgets.status_bar import StatusBar


class BrandLabel(Static):
    DEFAULT_CSS = "BrandLabel { width: auto; }"

    def render(self) -> Text:
        palette = halo_app(self).palette
        text = Text(no_wrap=True)
        text.append("◆ ", style=palette.accent)
        text.append("CLAUDE HALO", style="bold")
        text.append(f"  v{__version__}", style=palette.text_dim)
        return text


class ListeningStatus(Static):
    """« ● … » à droite de l'en-tête ; le point pulse doucement au repos."""

    DEFAULT_CSS = "ListeningStatus { width: 1fr; text-align: right; }"

    pulse = reactive(True)

    def on_mount(self) -> None:
        self.set_interval(1.2, self._tick)

    def _tick(self) -> None:
        if halo_app(self).motion.enabled:
            self.pulse = not self.pulse
        elif not self.pulse:
            self.pulse = True

    def render(self) -> Text:
        app = halo_app(self)
        text = Text(no_wrap=True, overflow="ellipsis", justify="right")
        dot_style = app.palette.accent if self.pulse else app.palette.accent_deep
        text.append("● ", style=dot_style)
        text.append(app.voice_status, style=app.palette.text_dim)
        return text


class DashboardHeader(Horizontal):
    DEFAULT_CSS = """
    DashboardHeader { height: 1; padding: 0 2; margin: 0 0 1 0; }
    """

    def compose(self) -> ComposeResult:
        yield BrandLabel()
        yield ListeningStatus()


class IdleScreen(Screen[None]):
    DEFAULT_CSS = """
    IdleScreen { align: center top; }
    IdleScreen > #dashboard {
        width: 100%;
        max-width: 104;
        height: 1fr;
        padding: 1 2 0 2;
    }
    IdleScreen.compact > #dashboard { padding: 0 2; }
    """

    def compose(self) -> ComposeResult:
        app = halo_app(self)
        with Vertical(id="dashboard"):
            yield DashboardHeader()
            yield ConfigPanel(build_sections(app), on_change=app.persist_settings)
        yield StatusBar()

    def on_mount(self) -> None:
        app = halo_app(self)
        self.set_class(app.settings.appearance.density == "compact", "compact")
        self.query_one(ConfigPanel).focus()
        self.query_one(StatusBar).set_hints(
            (
                ("↑ ↓", "naviguer"),
                ("◂ ▸", "modifier"),
                ("⏎", "ouvrir"),
                ("F2", "parler"),
                ("ctrl+q", "quitter"),
            )
        )
