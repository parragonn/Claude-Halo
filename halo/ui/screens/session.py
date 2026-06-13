"""Écran de session vocale : orbe, sous-titres, fil de réponses.

Chorégraphie (spec §5/§6.5) :
- WAKE : la scène apparaît en fondu, orbe centrée audio-réactive ;
- fin de question : l'orbe se déporte à gauche (rétrécissement du rail) EN MÊME
  TEMPS que le panneau se révèle à droite (fondu), 350 ms, ease in-out ;
- la réponse arrive dans un fil scrollable de tours proprement séparés ;
- les boutons de session vivent sous l'orbe et n'apparaissent que par fondu.
Reduced-motion : toutes les bascules sont instantanées.
"""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Center, Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Static

from halo.core import events as ev
from halo.core.models import Command, MachineState, Phase
from halo.ui.animation import DUR_SLOW, EASING
from halo.ui.app_link import halo_app
from halo.ui.widgets.orb import Orb
from halo.ui.widgets.orb_physics import OrbMode
from halo.ui.widgets.session_buttons import SessionButtons
from halo.ui.widgets.status_bar import StatusBar
from halo.ui.widgets.thread_view import NewReplyPill, ThreadView, TurnView

_STATE_LABEL = {
    Phase.LISTENING: "écoute…",
    Phase.THINKING: "réflexion…",
    Phase.RESPONDING: "réponse",
    Phase.SESSION_IDLE: "à l'écoute de « Claude, … »",
}

_RAIL_WIDTH = 30


class CaptionLine(Static):
    """Transcription partielle en dim, façon sous-titre, sous l'orbe."""

    DEFAULT_CSS = "CaptionLine { height: 2; margin: 1 2 0 2; }"

    caption = reactive("")

    def render(self) -> Text:
        palette = halo_app(self).palette
        return Text(self.caption, style=palette.text_dim, justify="center")


class StateDot(Static):
    DEFAULT_CSS = "StateDot { height: 1; margin: 0 2; }"

    label = reactive("")

    def render(self) -> Text:
        palette = halo_app(self).palette
        text = Text(justify="center", no_wrap=True)
        text.append("● ", style=palette.accent)
        text.append(self.label, style=palette.text_secondary)
        return text


class SessionScreen(Screen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Annuler", show=False),
    ]

    DEFAULT_CSS = """
    SessionScreen #stage { height: 1fr; }
    SessionScreen #rail { width: 1fr; padding: 1 0 0 0; }
    SessionScreen #orb-box { height: 20; }
    SessionScreen #panel { width: 1fr; padding: 1 2 0 1; display: none; }
    SessionScreen #panel-box {
        border: round $halo-border;
        padding: 1 2;
        height: 1fr;
    }
    SessionScreen.-split #orb-box { height: 12; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.orb = Orb(mode=OrbMode.LISTENING)
        self._caption = CaptionLine()
        self._dot = StateDot()
        self._thread = ThreadView()
        self._pill = NewReplyPill()
        self._buttons = SessionButtons()
        self._status = StatusBar()
        self._active_turn: TurnView | None = None
        self._split = False
        self._egg = ""

    def compose(self) -> ComposeResult:
        with Horizontal(id="stage"):
            with Vertical(id="rail"):
                with Center(id="orb-box"):
                    yield self.orb
                yield self._dot
                yield self._caption
                yield self._buttons
            with Vertical(id="panel"):
                with Vertical(id="panel-box"):
                    yield self._thread
                    yield self._pill
        yield self._status

    def on_mount(self) -> None:
        self._thread.attach_pill(self._pill)
        self.set_interval(0.1, self._flush_active)
        app = halo_app(self)
        if app.motion.enabled:  # apparition de la scène en fondu (WAKE)
            stage = self.query_one("#stage")
            stage.styles.opacity = 0.0
            stage.styles.animate("opacity", 1.0, duration=0.3, easing=EASING)
        self._apply_phase(app.coordinator_state())

    # ── chorégraphie fin de question ─────────────────────────────────────────

    def _enter_split(self) -> None:
        if self._split:
            return
        self._split = True
        rail = self.query_one("#rail")
        panel = self.query_one("#panel")
        panel.display = True
        self.set_class(True, "-split")
        if halo_app(self).motion.enabled:
            rail.styles.width = rail.size.width  # gèle la largeur avant l'animation
            rail.styles.animate("width", _RAIL_WIDTH, duration=DUR_SLOW, easing=EASING)
            panel.styles.opacity = 0.0
            panel.styles.animate("opacity", 1.0, duration=DUR_SLOW, easing=EASING)
        else:
            rail.styles.width = _RAIL_WIDTH
            panel.styles.opacity = 1.0

    # ── routage des événements du domaine ────────────────────────────────────

    def on_domain_event(self, event: ev.Event, state: MachineState) -> None:
        match event:
            case ev.AmplitudeChanged(level=level):
                self.orb.set_level(level)
            case ev.TranscriptPartial(text=text):
                self._caption.caption = text
            case ev.WakeDetected(residual_text=residual):
                self._caption.caption = residual
            case ev.TranscriptFinal():
                self._caption.caption = ""
            case ev.ResponseDelta(text=text):
                self.append_answer(text)
            case ev.ResponseCompleted():
                if self._active_turn is not None:
                    self._active_turn.finish()
            case _:
                pass
        self._apply_phase(state)

    def on_turn_started(self, question: str) -> None:
        app = halo_app(self)
        reveal = app.settings.appearance.reveal
        if not app.motion.enabled:
            reveal = "instant"
        turn = TurnView(
            question,
            reveal=reveal,
            animate_in=app.motion.enabled and reveal != "instant",
            followup=self._thread.turn_count > 0,
        )
        self._active_turn = turn
        self._thread.add_turn(turn)

    def append_answer(self, delta: str) -> None:
        if self._active_turn is not None:
            self._active_turn.append(delta)

    def show_failure(self, message: str) -> None:
        if self._active_turn is not None:
            self._active_turn.fail(message)
            self._thread.content_grew()

    def reset_thread(self) -> None:
        self._thread.clear_turns()
        self._active_turn = None
        self._caption.caption = ""

    def _flush_active(self) -> None:
        if self._active_turn is not None and self._active_turn.flush():
            self._thread.content_grew()

    # ── mise en page par phase ───────────────────────────────────────────────

    def _apply_phase(self, state: MachineState) -> None:
        phase = state.phase
        if phase in (Phase.THINKING, Phase.RESPONDING, Phase.SESSION_IDLE) or state.in_session:
            self._enter_split()
        if phase is Phase.LISTENING:
            self.orb.set_mode(OrbMode.LISTENING)
        elif phase is Phase.THINKING:
            self.orb.set_mode(OrbMode.THINKING)
        else:
            self.orb.set_mode(OrbMode.CALM)
        if state.in_session:
            self._buttons.reveal()
        else:
            self._buttons.conceal()
        self._dot.label = _STATE_LABEL.get(phase, "")
        hints: tuple[tuple[str, str], ...]
        if phase is Phase.SESSION_IDLE:
            hints = (
                ("« Claude, … »", "question suivante"),
                ("F2", "parler"),
                ("↑ ↓", "fil"),
                ("tab", "boutons"),
            )
            if not self._thread.has_focus and not self._buttons.active:
                self.set_focus(self._thread)
        else:
            hints = (("échap", "annuler"),)
        self._status.set_hints(hints)

    # ── actions clavier ──────────────────────────────────────────────────────

    def on_key(self, event: events.Key) -> None:
        key = event.key
        if self._buttons.active:
            if key in ("up", "down"):
                self._buttons.move(1 if key == "down" else -1)
            elif key == "enter":
                self._buttons.activate()
            elif key in ("tab", "escape"):
                self._set_buttons_active(False)
            else:
                return
        elif key == "tab" and self._split:
            self._set_buttons_active(True)
        else:
            if len(key) == 1 and key.isalpha():
                self._egg = (self._egg + key)[-7:]
                if self._egg == "rainbow":  # un secret discret, une seule pulsation
                    self.orb.rainbow_pulse()
            return
        event.stop()
        event.prevent_default()

    def _set_buttons_active(self, active: bool) -> None:
        self._buttons.set_active(active)
        if active:
            self.set_focus(None)  # les flèches pilotent les boutons, pas le fil
        else:
            self.set_focus(self._thread)

    def action_cancel(self) -> None:
        app = halo_app(self)
        command = (
            Command.BACK_HOME
            if app.coordinator_state().phase is Phase.SESSION_IDLE
            else Command.CANCEL
        )
        app.dispatch_command(command)
