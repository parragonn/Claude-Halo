"""Assistant de calibration micro : silence → voix → résultat, guidé.

Pilote MicCalibrator dans un thread et réagit à ses phases. Réutilise le
VU-mètre des modales vocales. Retourne le CalibrationResult accepté (ou None).
"""

from __future__ import annotations

import threading
from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Static

from halo.audio.calibration import CalibrationResult
from halo.audio.mic_calibrator import MicCalibrator
from halo.ui.app_link import halo_app
from halo.ui.widgets.voice_modals import VuMeter


class CalibrationModal(ModalScreen[CalibrationResult | None]):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("enter", "advance", "Suivant", show=False),
        Binding("r", "retry", "Refaire", show=False),
        Binding("escape", "cancel", "Annuler", show=False),
    ]

    DEFAULT_CSS = """
    CalibrationModal { align: center middle; }
    CalibrationModal > #dialog {
        width: 64; height: auto; padding: 1 2;
        border: round $halo-border;
    }
    CalibrationModal #title { color: $halo-accent; text-style: bold; }
    CalibrationModal #phase { height: 2; margin: 1 0 0 0; text-style: bold; }
    CalibrationModal #detail { height: auto; margin: 1 0 0 0; }
    CalibrationModal #hint { color: $halo-dim; margin: 1 0 0 0; }
    CalibrationModal VuMeter { margin: 1 0 0 0; }
    """

    _SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, calibrator: MicCalibrator, wake_phrase: str) -> None:
        super().__init__()
        self._calibrator = calibrator
        self._wake_phrase = wake_phrase
        self._stage = "intro"  # intro | running | result | error
        self._result: CalibrationResult | None = None
        self._transcript = ""
        self._spin_index = 0
        self._spin_label = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Calibration du micro", id="title")
            yield Static(id="phase")
            yield VuMeter()
            yield Static(id="detail")
            yield Static(id="hint")

    def on_mount(self) -> None:
        self.query_one(VuMeter).display = False
        self.set_interval(0.1, self._tick_spinner)
        self._render_intro()

    def _tick_spinner(self) -> None:
        if not self._spin_label:
            return
        self._spin_index = (self._spin_index + 1) % len(self._SPINNER)
        palette = halo_app(self).palette
        text = Text()
        text.append(self._SPINNER[self._spin_index] + " ", style=palette.accent)
        text.append(self._spin_label, style="bold")
        self.query_one("#phase", Static).update(text)

    # ── étapes ───────────────────────────────────────────────────────────────

    def _render_intro(self) -> None:
        self._stage = "intro"
        self._spin_label = ""
        palette = halo_app(self).palette
        self.query_one("#phase", Static).update(
            Text("Deux mesures rapides : un silence, puis ta voix.", style=palette.text_secondary)
        )
        self.query_one("#detail", Static).update(
            f"On va d'abord écouter 2 s de silence, puis tu diras « {self._wake_phrase} »."
        )
        self.query_one("#hint", Static).update("entrée commencer · échap annuler")

    def _start_pipeline(self) -> None:
        self._stage = "running"
        self.query_one(VuMeter).display = False
        self.query_one("#hint", Static).update("…")
        threading.Thread(target=self._job, name="halo-calibration", daemon=True).start()

    def _job(self) -> None:
        app = self.app
        self._calibrator.run(
            on_phase=lambda phase: app.call_from_thread(self._on_phase, phase),
            on_level=lambda level: app.call_from_thread(self._on_level, level),
            on_done=lambda result, text: app.call_from_thread(self._on_done, result, text),
            on_error=lambda detail: app.call_from_thread(self._on_error, detail),
        )

    def _on_phase(self, phase: str) -> None:
        palette = halo_app(self).palette
        vu = self.query_one(VuMeter)
        phase_widget = self.query_one("#phase", Static)
        self._spin_label = ""  # par défaut : pas de spinner
        if phase == "prepare":
            vu.display = False
            self._spin_label = "Préparation du modèle vocal…"
            self.query_one("#detail", Static).update("première fois : le chargement peut durer")
        elif phase == "noise":
            vu.display = False
            phase_widget.update(Text("🤫  Reste silencieux…", style=palette.accent))
            self.query_one("#detail", Static).update("mesure du bruit ambiant")
        elif phase == "voice":
            vu.display = True
            phase_widget.update(
                Text(f"🎙  Dis maintenant : « {self._wake_phrase} »", style=palette.accent)
            )
            self.query_one("#detail", Static).update("parle normalement, à 20–30 cm du micro")
        elif phase == "transcribe":
            vu.display = False
            self._spin_label = "Analyse…"
            self.query_one("#detail", Static).update("")

    def _on_level(self, level: float) -> None:
        self.query_one(VuMeter).set_level(level)

    def _on_done(self, result: CalibrationResult, transcript: str) -> None:
        self._stage = "result"
        self._spin_label = ""
        self._result = result
        self._transcript = transcript
        palette = halo_app(self).palette
        quality_color = {
            "excellent": palette.accent,
            "bon": palette.accent,
            "moyen": palette.text_secondary,
            "faible": palette.text_dim,
        }.get(result.quality, palette.text_secondary)
        header = Text()
        header.append("● ", style=palette.accent)
        header.append(f"Micro : {result.quality}", style=f"bold {quality_color}")
        header.append(f"   (SNR {result.snr:.0f}×)", style=palette.text_dim)
        self.query_one("#phase", Static).update(header)

        detail = Text()
        detail.append(result.message + "\n\n", style=palette.text_secondary)
        if transcript:
            detail.append("Halo a entendu : ", style=palette.text_dim)
            detail.append(f"« {transcript} »", style="italic")
        else:
            detail.append(
                "Rien de transcrit — vérifie le micro et réessaie.", style=palette.text_dim
            )
        self.query_one(VuMeter).display = False
        self.query_one("#detail", Static).update(detail)
        self.query_one("#hint", Static).update("entrée appliquer · r refaire · échap annuler")

    def _on_error(self, detail: str) -> None:
        self._stage = "error"
        self._spin_label = ""
        self.query_one(VuMeter).display = False
        self.query_one("#phase", Static).update(Text("Échec de la calibration", style="bold"))
        self.query_one("#detail", Static).update(detail)
        self.query_one("#hint", Static).update("r réessayer · échap fermer")

    # ── actions ──────────────────────────────────────────────────────────────

    def action_advance(self) -> None:
        if self._stage == "intro":
            self._start_pipeline()
        elif self._stage == "result":
            self.dismiss(self._result)

    def action_retry(self) -> None:
        if self._stage in ("result", "error"):
            self._render_intro()
            self._start_pipeline()

    def action_cancel(self) -> None:
        if self._stage != "running":
            self.dismiss(None)
