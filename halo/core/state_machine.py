"""Machine à états de Halo — réducteur pur : (état, événement) → (état, effets).

Aucune I/O : la chorégraphie réelle (fenêtre, micro, API, timers) est exécutée
par la composition root à partir des effets retournés. Un événement non pertinent
dans la phase courante est ignoré (état inchangé, zéro effet).
"""

from __future__ import annotations

from collections.abc import Callable

from halo.core import events as ev
from halo.core.models import Command, MachineState, Phase, TimerId

type Result = tuple[MachineState, tuple[ev.Effect, ...]]


def initial_state() -> MachineState:
    return MachineState(phase=Phase.IDLE, in_session=False)


def _resting(in_session: bool, *lead: ev.Effect) -> Result:
    """Retour au repos : fil de session (avec minuterie d'inactivité) ou accueil."""
    if in_session:
        effects = (*lead, ev.StartTimer(TimerId.SESSION_IDLE_TIMEOUT))
        return MachineState(Phase.SESSION_IDLE, in_session=True), effects
    return MachineState(Phase.IDLE, in_session=False), tuple(lead)


def _accept_transcript(state: MachineState, text: str, *lead: ev.Effect) -> Result:
    """Question vide (rien d'intelligible) → repos ; sinon → envoi au modèle."""
    prompt = text.strip()
    if not prompt:
        return _resting(state.in_session, *lead)
    return (
        MachineState(Phase.THINKING, state.in_session),
        (*lead, ev.SubmitPrompt(prompt=prompt)),
    )


def _reduce_idle(state: MachineState, event: ev.Event) -> Result | None:
    match event:
        case ev.WakeDetected(residual_text=seed):
            return (
                MachineState(Phase.LISTENING, in_session=False),
                (ev.BringTerminalToForeground(), ev.StartCapture(seed_text=seed)),
            )
        case ev.UserCommand(command=Command.MANUAL_WAKE):
            # Déclenché au clavier : le terminal a déjà le focus.
            return MachineState(Phase.LISTENING, in_session=False), (ev.StartCapture(),)
    return None


def _reduce_listening(state: MachineState, event: ev.Event) -> Result | None:
    match event:
        case ev.SpeechEnded():
            return MachineState(Phase.THINKING, state.in_session), (ev.StopCapture(),)
        case ev.TranscriptFinal(text=text):
            # Finale arrivée sans SpeechEnded préalable : même traitement.
            return _accept_transcript(state, text, ev.StopCapture())
        case ev.UserCommand(command=Command.CANCEL) | ev.AudioFault():
            return _resting(state.in_session, ev.StopCapture())
    return None


def _reduce_thinking(state: MachineState, event: ev.Event) -> Result | None:
    match event:
        case ev.TranscriptFinal(text=text):
            return _accept_transcript(state, text)
        case ev.ResponseDelta():
            return MachineState(Phase.RESPONDING, in_session=True), ()
        case ev.ResponseCompleted():
            return _resting(True)
        case ev.ResponseFailed():
            return _resting(True)
        case ev.UserCommand(command=Command.CANCEL):
            return _resting(state.in_session, ev.CancelResponse())
    return None


def _reduce_responding(state: MachineState, event: ev.Event) -> Result | None:
    match event:
        case ev.ResponseCompleted():
            return _resting(True)
        case ev.ResponseFailed():
            return _resting(True)
        case ev.UserCommand(command=Command.CANCEL):
            return _resting(True, ev.CancelResponse())
    return None


def _reduce_session_idle(state: MachineState, event: ev.Event) -> Result | None:
    stop_idle = ev.StopTimer(TimerId.SESSION_IDLE_TIMEOUT)
    match event:
        case ev.WakeDetected(residual_text=seed):
            return (
                MachineState(Phase.LISTENING, in_session=True),
                (stop_idle, ev.BringTerminalToForeground(), ev.StartCapture(seed_text=seed)),
            )
        case ev.UserCommand(command=Command.MANUAL_WAKE):
            return (
                MachineState(Phase.LISTENING, in_session=True),
                (stop_idle, ev.StartCapture()),
            )
        case ev.UserCommand(command=Command.NEW_SESSION):
            return (
                MachineState(Phase.SESSION_IDLE, in_session=True),
                (ev.ResetSession(), stop_idle, ev.StartTimer(TimerId.SESSION_IDLE_TIMEOUT)),
            )
        case ev.UserCommand(command=Command.BACK_HOME):
            return (
                MachineState(Phase.IDLE, in_session=False),
                (ev.ResetSession(), stop_idle),
            )
        case ev.UserCommand(command=Command.RETRY):
            return (
                MachineState(Phase.THINKING, in_session=True),
                (stop_idle, ev.ResubmitLastPrompt()),
            )
        case ev.TimerFired(timer=TimerId.SESSION_IDLE_TIMEOUT):
            return MachineState(Phase.IDLE, in_session=False), (ev.ResetSession(),)
    return None


_HANDLERS: dict[Phase, Callable[[MachineState, ev.Event], Result | None]] = {
    Phase.IDLE: _reduce_idle,
    Phase.LISTENING: _reduce_listening,
    Phase.THINKING: _reduce_thinking,
    Phase.RESPONDING: _reduce_responding,
    Phase.SESSION_IDLE: _reduce_session_idle,
}


def reduce(state: MachineState, event: ev.Event) -> Result:
    result = _HANDLERS[state.phase](state, event)
    if result is None:
        return state, ()
    return result


class StateMachine:
    """Détient l'état courant ; `dispatch` applique le réducteur pur."""

    def __init__(self) -> None:
        self.state = initial_state()

    def dispatch(self, event: ev.Event) -> Result:
        self.state, effects = reduce(self.state, event)
        return self.state, effects
