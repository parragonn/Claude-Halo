"""Logique d'une conversation : fil de tours, contexte envoyé au modèle.

Mutable mais sans I/O ; la persistance opt-in de l'historique vit ailleurs.
"""

from __future__ import annotations

from halo.core.models import FailureKind, Turn


class Session:
    def __init__(self, max_context_turns: int = 20) -> None:
        self._turns: list[Turn] = []
        self._max_context_turns = max_context_turns

    @property
    def turns(self) -> tuple[Turn, ...]:
        return tuple(self._turns)

    @property
    def is_empty(self) -> bool:
        return not self._turns

    @property
    def open_turn(self) -> Turn | None:
        if self._turns and not self._turns[-1].completed:
            return self._turns[-1]
        return None

    @property
    def last_question(self) -> str | None:
        return self._turns[-1].question if self._turns else None

    def begin_turn(self, question: str) -> Turn:
        turn = Turn(question=question.strip())
        self._turns.append(turn)
        return turn

    def append_delta(self, text: str) -> None:
        turn = self.open_turn
        if turn is not None:
            turn.answer += text

    def complete_turn(self) -> None:
        turn = self.open_turn
        if turn is not None:
            turn.completed = True

    def fail_turn(self, kind: FailureKind, hint: str = "") -> None:
        turn = self.open_turn
        if turn is not None:
            turn.error = kind
            turn.error_hint = hint
            turn.completed = True

    def reset(self) -> None:
        self._turns.clear()

    def to_messages(self) -> list[dict[str, str]]:
        """Contexte au format Messages API (rôles alternés user/assistant).

        Les tours en échec sans aucun contenu sont omis ; une réponse partielle
        (annulée en cours) est conservée — l'utilisateur l'a vue.
        """
        messages: list[dict[str, str]] = []
        for turn in self._turns[-self._max_context_turns :]:
            if turn.error is not None and not turn.answer:
                continue
            messages.append({"role": "user", "content": turn.question})
            if turn.answer:
                messages.append({"role": "assistant", "content": turn.answer})
        return messages
