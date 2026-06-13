"""Faux moteur vocal : rejoue une « question parlée » scriptée.

Permet de vérifier tout le parcours (orbe réactive, sous-titres, chorégraphie,
réponse) sans micro ni modèle — utilisé par `halo --demo` et les tests.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable

from halo.core import events as ev


class FakeVoiceEngine:
    def __init__(
        self,
        emit: Callable[[ev.Event], None],
        *,
        question: str = "Explique-moi les quaternions simplement.",
        speed: float = 1.0,
    ) -> None:
        self._emit = emit
        self.question = question
        self._speed = max(0.05, speed)
        self._generation = 0

    # ── port VoiceEngine ─────────────────────────────────────────────────────

    def start(self) -> bool:
        return True

    def stop(self) -> None:
        self._generation += 1

    def start_capture(self) -> None:
        self._generation += 1
        threading.Thread(
            target=self._script, args=(self._generation,), name="halo-fake-voice", daemon=True
        ).start()

    def stop_capture(self) -> None:
        self._generation += 1

    def set_followup_mode(self, enabled: bool) -> None:
        pass

    # ── déclencheurs de scénario ─────────────────────────────────────────────

    def trigger_wake(self, residual: str = "") -> None:
        self._emit(ev.WakeDetected(residual_text=residual))

    def _sleep(self, seconds: float) -> None:
        time.sleep(seconds / self._speed)

    def _script(self, generation: int) -> None:
        words = self.question.split()
        speak_s = max(1.6, 0.34 * len(words))
        self._sleep(0.25)
        if generation != self._generation:
            return
        self._emit(ev.SpeechStarted())
        steps = max(8, int(speak_s * 30))
        next_partial = 0.45
        for i in range(steps):
            if generation != self._generation:
                return
            t = (i / 30.0) * 1.0
            burst = max(0.0, math.sin(t * 3.1)) ** 1.4
            self._emit(ev.AmplitudeChanged(level=0.15 + 0.8 * burst))
            elapsed = (i + 1) / steps * speak_s
            if elapsed >= next_partial:
                count = max(1, round(len(words) * elapsed / speak_s))
                self._emit(ev.TranscriptPartial(text=" ".join(words[:count])))
                next_partial += 0.55
            self._sleep(1 / 30)
        self._emit(ev.AmplitudeChanged(level=0.05))
        self._emit(ev.SpeechEnded())
        # Comme le vrai moteur : une fois la parole terminée, la finale part
        # quoi qu'il arrive (le StopCapture qui suit SpeechEnded ne l'annule pas).
        self._sleep(0.45)
        self._emit(ev.TranscriptFinal(text=self.question))
