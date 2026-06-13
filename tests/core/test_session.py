"""Cycle de vie des tours et format du contexte envoyé au modèle."""

from __future__ import annotations

from halo.core.models import FailureKind
from halo.core.session import Session


def test_turn_lifecycle() -> None:
    session = Session()
    assert session.is_empty
    session.begin_turn("  ma question  ")
    assert session.last_question == "ma question"
    session.append_delta("dé")
    session.append_delta("but")
    assert session.open_turn is not None
    assert session.open_turn.answer == "début"
    session.complete_turn()
    assert session.open_turn is None
    assert session.turns[0].completed


def test_to_messages_includes_open_question_last() -> None:
    session = Session()
    session.begin_turn("q1")
    session.append_delta("r1")
    session.complete_turn()
    session.begin_turn("q2")
    assert session.to_messages() == [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "r1"},
        {"role": "user", "content": "q2"},
    ]


def test_failed_turn_without_content_is_excluded_from_context() -> None:
    session = Session()
    session.begin_turn("q1")
    session.fail_turn(FailureKind.OFFLINE, hint="hors-ligne")
    session.begin_turn("q2")
    assert session.to_messages() == [{"role": "user", "content": "q2"}]
    assert session.turns[0].error is FailureKind.OFFLINE


def test_cancelled_partial_answer_stays_in_context() -> None:
    session = Session()
    session.begin_turn("q1")
    session.append_delta("réponse partielle")
    session.complete_turn()
    assert {"role": "assistant", "content": "réponse partielle"} in session.to_messages()


def test_context_window_caps_old_turns() -> None:
    session = Session(max_context_turns=2)
    for i in range(4):
        session.begin_turn(f"q{i}")
        session.append_delta(f"r{i}")
        session.complete_turn()
    messages = session.to_messages()
    assert messages[0] == {"role": "user", "content": "q2"}
    assert len(messages) == 4


def test_append_without_open_turn_is_noop() -> None:
    session = Session()
    session.append_delta("perdu")
    assert session.is_empty


def test_reset_clears_thread() -> None:
    session = Session()
    session.begin_turn("q")
    session.reset()
    assert session.is_empty
    assert session.last_question is None
