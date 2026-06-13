"""Tests en table du réducteur — le chemin critique de toute l'app."""

from __future__ import annotations

from halo.core import events as ev
from halo.core.models import (
    AudioFaultKind,
    Command,
    FailureKind,
    MachineState,
    Phase,
    TimerId,
)
from halo.core.state_machine import StateMachine, initial_state, reduce


def kinds(effects: tuple[ev.Effect, ...]) -> list[type]:
    return [type(e) for e in effects]


def in_session_machine() -> StateMachine:
    """Machine amenée en SESSION_IDLE par le parcours nominal complet."""
    sm = StateMachine()
    sm.dispatch(ev.WakeDetected())
    sm.dispatch(ev.SpeechEnded())
    sm.dispatch(ev.TranscriptFinal(text="première question"))
    sm.dispatch(ev.ResponseDelta(text="début de réponse"))
    sm.dispatch(ev.ResponseCompleted())
    assert sm.state == MachineState(Phase.SESSION_IDLE, in_session=True)
    return sm


def test_initial_state() -> None:
    assert initial_state() == MachineState(Phase.IDLE, in_session=False)


def test_wake_from_idle_brings_foreground_then_captures() -> None:
    state, effects = reduce(initial_state(), ev.WakeDetected(residual_text="quelle heure"))
    assert state == MachineState(Phase.LISTENING, in_session=False)
    assert kinds(effects) == [ev.BringTerminalToForeground, ev.StartCapture]
    capture = effects[1]
    assert isinstance(capture, ev.StartCapture)
    assert capture.seed_text == "quelle heure"


def test_manual_wake_does_not_steal_focus() -> None:
    state, effects = reduce(initial_state(), ev.UserCommand(Command.MANUAL_WAKE))
    assert state.phase is Phase.LISTENING
    assert kinds(effects) == [ev.StartCapture]


def test_happy_path_step_by_step() -> None:
    sm = StateMachine()
    sm.dispatch(ev.WakeDetected())

    state, effects = sm.dispatch(ev.SpeechEnded())
    assert state.phase is Phase.THINKING
    assert kinds(effects) == [ev.StopCapture]

    state, effects = sm.dispatch(ev.TranscriptFinal(text=" explique les quaternions "))
    assert state.phase is Phase.THINKING
    assert kinds(effects) == [ev.SubmitPrompt]
    submit = effects[0]
    assert isinstance(submit, ev.SubmitPrompt)
    assert submit.prompt == "explique les quaternions"

    state, effects = sm.dispatch(ev.ResponseDelta(text="Les quaternions"))
    assert state == MachineState(Phase.RESPONDING, in_session=True)
    assert effects == ()

    state, effects = sm.dispatch(ev.ResponseCompleted())
    assert state == MachineState(Phase.SESSION_IDLE, in_session=True)
    assert kinds(effects) == [ev.StartTimer]


def test_transcript_final_while_listening_submits_directly() -> None:
    sm = StateMachine()
    sm.dispatch(ev.WakeDetected())
    state, effects = sm.dispatch(ev.TranscriptFinal(text="question directe"))
    assert state.phase is Phase.THINKING
    assert kinds(effects) == [ev.StopCapture, ev.SubmitPrompt]


def test_empty_transcript_returns_home_before_any_session() -> None:
    sm = StateMachine()
    sm.dispatch(ev.WakeDetected())
    sm.dispatch(ev.SpeechEnded())
    state, effects = sm.dispatch(ev.TranscriptFinal(text="   "))
    assert state == MachineState(Phase.IDLE, in_session=False)
    assert effects == ()


def test_empty_transcript_in_session_returns_to_thread() -> None:
    sm = in_session_machine()
    sm.dispatch(ev.WakeDetected())
    sm.dispatch(ev.SpeechEnded())
    state, effects = sm.dispatch(ev.TranscriptFinal(text=""))
    assert state == MachineState(Phase.SESSION_IDLE, in_session=True)
    assert ev.StartTimer in kinds(effects)


def test_followup_wake_stops_idle_timer_and_keeps_session() -> None:
    sm = in_session_machine()
    state, effects = sm.dispatch(ev.WakeDetected(residual_text="et ensuite"))
    assert state == MachineState(Phase.LISTENING, in_session=True)
    assert kinds(effects) == [ev.StopTimer, ev.BringTerminalToForeground, ev.StartCapture]


def test_idle_timeout_resets_session_and_goes_home() -> None:
    sm = in_session_machine()
    state, effects = sm.dispatch(ev.TimerFired(TimerId.SESSION_IDLE_TIMEOUT))
    assert state == MachineState(Phase.IDLE, in_session=False)
    assert kinds(effects) == [ev.ResetSession]


def test_back_home_resets_session() -> None:
    sm = in_session_machine()
    state, effects = sm.dispatch(ev.UserCommand(Command.BACK_HOME))
    assert state == MachineState(Phase.IDLE, in_session=False)
    assert ev.ResetSession in kinds(effects)
    assert ev.StopTimer in kinds(effects)


def test_new_session_clears_thread_but_stays_in_session_view() -> None:
    sm = in_session_machine()
    state, effects = sm.dispatch(ev.UserCommand(Command.NEW_SESSION))
    assert state == MachineState(Phase.SESSION_IDLE, in_session=True)
    assert ev.ResetSession in kinds(effects)
    assert ev.StartTimer in kinds(effects)


def test_retry_resubmits_last_prompt() -> None:
    sm = in_session_machine()
    state, effects = sm.dispatch(ev.UserCommand(Command.RETRY))
    assert state == MachineState(Phase.THINKING, in_session=True)
    assert ev.ResubmitLastPrompt in kinds(effects)


def test_response_failure_lands_in_session_thread() -> None:
    sm = StateMachine()
    sm.dispatch(ev.WakeDetected())
    sm.dispatch(ev.SpeechEnded())
    sm.dispatch(ev.TranscriptFinal(text="question"))
    state, effects = sm.dispatch(ev.ResponseFailed(kind=FailureKind.OFFLINE))
    assert state == MachineState(Phase.SESSION_IDLE, in_session=True)
    assert ev.StartTimer in kinds(effects)


def test_cancel_while_listening_first_time_goes_home() -> None:
    sm = StateMachine()
    sm.dispatch(ev.WakeDetected())
    state, effects = sm.dispatch(ev.UserCommand(Command.CANCEL))
    assert state == MachineState(Phase.IDLE, in_session=False)
    assert kinds(effects) == [ev.StopCapture]


def test_cancel_while_responding_keeps_session() -> None:
    sm = StateMachine()
    sm.dispatch(ev.WakeDetected())
    sm.dispatch(ev.SpeechEnded())
    sm.dispatch(ev.TranscriptFinal(text="question"))
    sm.dispatch(ev.ResponseDelta(text="dé"))
    state, effects = sm.dispatch(ev.UserCommand(Command.CANCEL))
    assert state == MachineState(Phase.SESSION_IDLE, in_session=True)
    assert ev.CancelResponse in kinds(effects)


def test_audio_fault_while_listening_aborts_capture() -> None:
    sm = StateMachine()
    sm.dispatch(ev.WakeDetected())
    state, effects = sm.dispatch(ev.AudioFault(kind=AudioFaultKind.DEVICE_LOST))
    assert state == MachineState(Phase.IDLE, in_session=False)
    assert kinds(effects) == [ev.StopCapture]


def test_wake_is_ignored_while_responding() -> None:
    sm = StateMachine()
    sm.dispatch(ev.WakeDetected())
    sm.dispatch(ev.SpeechEnded())
    sm.dispatch(ev.TranscriptFinal(text="question"))
    sm.dispatch(ev.ResponseDelta(text="dé"))
    before = sm.state
    state, effects = sm.dispatch(ev.WakeDetected())
    assert state == before
    assert effects == ()


def test_high_frequency_events_are_neutral() -> None:
    state, effects = reduce(initial_state(), ev.AmplitudeChanged(level=0.7))
    assert state == initial_state()
    assert effects == ()
