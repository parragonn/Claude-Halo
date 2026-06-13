"""Onboarding : la toute première impression, irréprochable et minimale.

Affiché uniquement quand aucune configuration n'existe encore : une carte
centrée, l'état des trois prérequis, et trois actions au clavier. Tout reste
modifiable ensuite dans le tableau de bord.
"""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Center, Middle, Vertical
from textual.screen import Screen
from textual.widgets import Static

from halo.ui.app_link import halo_app
from halo.ui.widgets.status_bar import StatusBar


class ChecklistLine(Static):
    DEFAULT_CSS = "ChecklistLine { height: 1; }"

    def __init__(self, label: str, check: object) -> None:
        super().__init__()
        self._label = label
        self._check = check

    def render(self) -> Text:
        palette = halo_app(self).palette
        ok = bool(self._check()) if callable(self._check) else bool(self._check)
        text = Text(no_wrap=True)
        if ok:
            text.append("✓ ", style=palette.accent)
            text.append(self._label, style=palette.text_secondary)
        else:
            text.append("○ ", style=palette.text_dim)
            text.append(self._label, style=palette.text_dim)
        return text


class OnboardingScreen(Screen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("k", "set_key", "Clé d'API", show=False),
        Binding("d", "download", "Modèles", show=False),
        Binding("c", "calibrate", "Calibrer", show=False),
        Binding("enter", "proceed", "Entrer", show=False),
        Binding("escape", "proceed", "Entrer", show=False),
    ]

    DEFAULT_CSS = """
    OnboardingScreen #card {
        width: 62; height: auto;
        border: round $halo-border;
        padding: 1 3;
    }
    OnboardingScreen #brand { text-style: bold; }
    OnboardingScreen #tagline { color: $halo-dim; margin: 0 0 1 0; }
    OnboardingScreen #checks { height: auto; margin: 1 0; }
    OnboardingScreen #accel-hint { color: $halo-accent; height: auto; }
    """

    def compose(self) -> ComposeResult:
        app = halo_app(self)
        with Middle(), Center():
            with Vertical(id="card"):
                yield Static(self._brand(), id="brand")
                yield Static("un assistant vocal, dans ton terminal", id="tagline")
                with Vertical(id="checks"):
                    yield ChecklistLine(
                        "clé d'API Anthropic (touche k)",
                        lambda: app.secrets.get_api_key() is not None,
                    )
                    yield ChecklistLine(
                        "modèles vocaux locaux (touche d)",
                        lambda: not app.models_missing(),
                    )
                    yield ChecklistLine(
                        "micro calibré (touche c)", lambda: app.settings.voice.calibrated
                    )
                    if app.accel is not None:
                        accel = app.accel
                        yield ChecklistLine(
                            accel.label, lambda: accel.cuda_ready or accel.kind != "nvidia"
                        )
                        if accel.hint:
                            yield Static(f"  → {accel.hint}", id="accel-hint")
                yield Static(self._footer())
        yield StatusBar()

    def _brand(self) -> Text:
        palette = halo_app(self).palette
        text = Text(no_wrap=True)
        text.append("◆ ", style=palette.accent)
        text.append("CLAUDE HALO")
        return text

    def _footer(self) -> Text:
        palette = halo_app(self).palette
        text = Text()
        text.append("dis « ", style=palette.text_dim)
        text.append(halo_app(self).settings.voice.wake_phrase, style=palette.accent)
        text.append(" » — ou appuie sur F2", style=palette.text_dim)
        return text

    def on_mount(self) -> None:
        self.query_one(StatusBar).set_hints(
            (
                ("k", "clé d'API"),
                ("d", "modèles"),
                ("c", "calibrer le micro"),
                ("⏎", "entrer"),
            )
        )

    def _refresh_checks(self) -> None:
        for line in self.query(ChecklistLine):
            line.refresh()

    def action_set_key(self) -> None:
        from halo.ui.widgets.modals import EditModal

        def done(value: str | None) -> None:
            if value and value.strip():
                if halo_app(self).secrets.set_api_key(value):
                    self.notify("Clé enregistrée dans le trousseau de l'OS.")
                self._refresh_checks()

        self.app.push_screen(
            EditModal(
                title="Clé d'API Anthropic (stockée dans le trousseau)",
                mask=True,
                placeholder="sk-ant-…",
            ),
            done,
        )

    def action_download(self) -> None:
        app = halo_app(self)

        def after(ok: bool | None) -> None:
            self._refresh_checks()
            if ok:
                app.start_voice_engine()

        if not app.models_missing():
            self.notify("Modèles vocaux déjà prêts ✓")
            return
        from halo.ui.widgets.voice_modals import DownloadModal

        self.app.push_screen(DownloadModal(app.models_missing(), app.model_downloader), after)

    def action_calibrate(self) -> None:
        app = halo_app(self)

        def after() -> None:
            self._refresh_checks()

        app.run_calibration()
        app.call_after_refresh(after)

    def action_proceed(self) -> None:
        app = halo_app(self)
        app.persist_settings()  # matérialise la config : l'onboarding ne revient plus
        self.dismiss(None)
