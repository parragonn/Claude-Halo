"""Coordinateur runtime : machine à états pure ↔ adapters (UI, audio, IA, OS).

Tourne sur la boucle UI. Les threads (audio, stt) y entrent via le wrapper
thread-safe construit par la composition root. Exécute les effets du réducteur
et tient la session ; ne contient aucune logique de domaine (elle vit dans
halo.core) ni de rendu (halo.ui).
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

from textual.message import Message

from halo.ai.ports import PromptRequest, ResponseProvider
from halo.audio.ports import VoiceEngine
from halo.config.history import HistoryStore
from halo.config.settings import Settings
from halo.core import events as ev
from halo.core.models import FailureKind, TimerId
from halo.core.session import Session
from halo.core.state_machine import StateMachine
from halo.platform.ports import WindowManager

if TYPE_CHECKING:
    from textual.timer import Timer

    from halo.ui.tui_app import HaloApp


class DomainEventMessage(Message):
    """Enveloppe Textual d'un événement du domaine venu d'un autre thread —
    traité par la pompe de messages de l'app, donc dans son contexte."""

    def __init__(self, event: ev.Event) -> None:
        super().__init__()
        self.event = event


def make_emitter(app: HaloApp) -> Callable[[ev.Event], None]:
    """Entrée thread-safe et NON bloquante des threads (audio, stt) vers la
    boucle UI. À construire sur le thread qui lance l'app."""
    ui_thread = threading.get_ident()

    def emit(event: ev.Event) -> None:
        coordinator = app.coordinator
        if coordinator is None:
            return
        if threading.get_ident() == ui_thread:
            coordinator.handle(event)
        else:
            app.post_message(DomainEventMessage(event))

    return emit


class Coordinator:
    def __init__(
        self,
        *,
        app: HaloApp,
        settings: Settings,
        provider: ResponseProvider,
        engine: VoiceEngine | None = None,
        window: WindowManager | None = None,
        history: HistoryStore | None = None,
    ) -> None:
        self._app = app
        self._settings = settings
        self.engine = engine
        self._provider = provider
        self._window = window
        self._history = history
        self.machine = StateMachine()
        self.session = Session()
        self._timers: dict[TimerId, Timer] = {}
        self._ai_task: asyncio.Task[None] | None = None

    # ── point d'entrée unique des événements (boucle UI) ─────────────────────

    def handle(self, event: ev.Event) -> None:
        if isinstance(event, ev.ResponseDelta):
            self.session.append_delta(event.text)
        elif isinstance(event, ev.ResponseCompleted):
            self.session.complete_turn()
            self._record_turn()
        elif isinstance(event, ev.ResponseFailed):
            self.session.fail_turn(event.kind, event.hint)

        previous = self.machine.state
        state, effects = self.machine.dispatch(event)
        if self.engine is not None and previous.in_session != state.in_session:
            self.engine.set_followup_mode(state.in_session)
        self._app.on_domain_event(event, previous, state)
        for effect in effects:
            self._run_effect(effect)

    # ── exécution des effets ─────────────────────────────────────────────────

    def _run_effect(self, effect: ev.Effect) -> None:
        match effect:
            case ev.StartCapture():
                if self.engine is not None:
                    self.engine.start_capture()
            case ev.StopCapture():
                if self.engine is not None:
                    self.engine.stop_capture()
            case ev.BringTerminalToForeground():
                if self._window is not None:
                    self._window.bring_to_foreground()
            case ev.SubmitPrompt(prompt=prompt):
                self._submit(prompt)
            case ev.ResubmitLastPrompt():
                question = self.session.last_question
                if question:
                    self._submit(question)
                else:
                    self.handle(
                        ev.ResponseFailed(kind=FailureKind.UNKNOWN, hint="rien à rejouer")
                    )
            case ev.CancelResponse():
                if self._ai_task is not None and not self._ai_task.done():
                    self._ai_task.cancel()
                self.session.complete_turn()
            case ev.StartTimer(timer=timer):
                self._start_timer(timer)
            case ev.StopTimer(timer=timer):
                handle = self._timers.pop(timer, None)
                if handle is not None:
                    handle.stop()
            case ev.ResetSession():
                self.session.reset()
                self._app.on_session_reset()

    def _record_turn(self) -> None:
        if self._history is None or not self._settings.system.history_enabled:
            return
        turns = self.session.turns
        if turns and turns[-1].answer:
            self._history.append_turn(
                question=turns[-1].question,
                answer=turns[-1].answer,
                model=self._settings.ai.model,
            )

    def clear_history(self) -> bool:
        return self._history.clear() if self._history is not None else False

    def _start_timer(self, timer: TimerId) -> None:
        previous = self._timers.pop(timer, None)
        if previous is not None:
            previous.stop()
        delay = self._settings.system.idle_return_s
        self._timers[timer] = self._app.set_timer(
            delay, lambda: self.handle(ev.TimerFired(timer=timer))
        )

    def _submit(self, prompt: str) -> None:
        turn = self.session.begin_turn(prompt)
        self._app.on_turn_started(turn)
        request = PromptRequest(
            messages=tuple(self.session.to_messages()),
            model=self._settings.ai.model,
            effort=self._settings.ai.effort,
            system_prompt=self._settings.ai.system_prompt,
            language=self._settings.ai.language,
            max_tokens=self._settings.ai.max_tokens,
        )
        if self._ai_task is not None and not self._ai_task.done():
            self._ai_task.cancel()

        async def runner() -> None:
            try:
                await self._provider.respond(request, self.handle)
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                self.handle(
                    ev.ResponseFailed(kind=FailureKind.UNKNOWN, hint=str(exc)[:120])
                )

        self._ai_task = asyncio.create_task(runner())
