"""Modales vocales : VU-mètre live du micro, téléchargement des modèles."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, ProgressBar, Static

from halo.ui.app_link import halo_app

_VU_WIDTH = 40


class VuMeter(Static):
    DEFAULT_CSS = "VuMeter { height: 1; margin: 1 0; }"

    def __init__(self) -> None:
        super().__init__()
        self._level = 0.0
        self._peak = 0.0

    def set_level(self, level: float) -> None:
        self._level = level
        self._peak = max(self._peak * 0.96, level)
        self.refresh()

    def render(self) -> Text:
        palette = halo_app(self).palette
        filled = round(self._level * _VU_WIDTH)
        peak = min(_VU_WIDTH - 1, round(self._peak * _VU_WIDTH))
        text = Text(no_wrap=True)
        for i in range(_VU_WIDTH):
            if i < filled:
                text.append("█", style=palette.accent)
            elif i == peak and peak > filled:
                text.append("▌", style=palette.accent_soft)
            else:
                text.append("·", style=palette.border)
        text.append(f"  {round(self._level * 100):>3} %", style=palette.text_secondary)
        return text


class MicTestModal(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Fermer", show=False),
    ]

    DEFAULT_CSS = """
    MicTestModal { align: center middle; }
    MicTestModal > #dialog {
        width: 58; height: auto; padding: 1 2;
        border: round $halo-border;
    }
    MicTestModal #title { color: $halo-accent; text-style: bold; }
    MicTestModal #hint { color: $halo-dim; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Test du micro", id="title")
            yield VuMeter()
            yield Static("parle : la barre doit suivre ta voix · échap fermer", id="hint")

    def on_mount(self) -> None:
        halo_app(self).mic_level_sink = self.query_one(VuMeter).set_level

    def on_unmount(self) -> None:
        halo_app(self).mic_level_sink = None

    def action_close(self) -> None:
        self.dismiss(None)


class DownloadModal(ModalScreen[bool]):
    """Téléchargement (thread) des modèles Whisper manquants, avec progression réelle."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "maybe_close", "Fermer", show=False),
    ]

    DEFAULT_CSS = """
    DownloadModal { align: center middle; }
    DownloadModal > #dialog {
        width: 64; height: auto; padding: 1 2;
        border: round $halo-border;
    }
    DownloadModal #title { color: $halo-accent; text-style: bold; }
    DownloadModal #detail { color: $halo-secondary; margin: 1 0 0 0; }
    DownloadModal #note { color: $halo-dim; margin: 1 0 0 0; }
    DownloadModal ProgressBar { margin: 1 0 0 0; }
    """

    def __init__(
        self, sizes: list[str], download: Callable[[str, Callable[[int, int], None]], None]
    ) -> None:
        super().__init__()
        self._sizes = sizes
        self._download = download
        self._busy = False
        self._failed = False

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Modèles vocaux (Whisper local)", id="title")
            yield Static("", id="detail")
            yield ProgressBar(total=None, show_eta=False)
            yield Static(
                "une seule fois — l'audio ne quitte jamais cette machine", id="note"
            )

    def on_mount(self) -> None:
        self._busy = True
        threading.Thread(target=self._job, name="halo-download", daemon=True).start()

    def _job(self) -> None:
        app = self.app
        try:
            for size in self._sizes:
                app.call_from_thread(self._set_detail, f"téléchargement de « {size} »…", size)
                throttle = [0.0]

                def report(
                    done: int,
                    total: int,
                    size: str = size,
                    last: list[float] = throttle,
                ) -> None:
                    now = time.monotonic()
                    if now - last[0] < 0.1 and (total == 0 or done < total):
                        return  # ~10 mises à jour/s suffisent à la barre
                    last[0] = now
                    app.call_from_thread(self._set_progress, size, done, total)

                self._download(size, report)
            app.call_from_thread(self.dismiss, True)
        except Exception as exc:
            app.call_from_thread(self._fail, str(exc)[:120])

    def _set_detail(self, text: str, _size: str = "") -> None:
        self.query_one("#detail", Static).update(text)
        self.query_one(ProgressBar).update(total=None)

    def _set_progress(self, size: str, done: int, total: int) -> None:
        bar = self.query_one(ProgressBar)
        if total > 0:
            bar.update(total=total, progress=min(done, total))
            done_mb, total_mb = done / 1_048_576, total / 1_048_576
            self.query_one("#detail", Static).update(
                f"téléchargement de « {size} »… {done_mb:,.0f} / {total_mb:,.0f} Mo".replace(
                    ",", " "
                )
            )
        else:
            bar.update(total=None)  # taille inconnue : pulsation

    def _fail(self, detail: str) -> None:
        self._busy = False
        self._failed = True
        self.query_one("#detail", Static).update(f"échec : {detail}")
        self.query_one("#note", Static).update("vérifie la connexion puis réessaie · échap fermer")

    def action_maybe_close(self) -> None:
        if not self._busy:
            self.dismiss(False)
