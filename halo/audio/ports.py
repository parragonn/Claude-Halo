"""Port du moteur vocal.

Le moteur tourne dans ses propres threads et publie des événements du domaine
(`WakeDetected`, `AmplitudeChanged`, `TranscriptPartial/Final`, `SpeechEnded`,
`AudioFault`) via le callback `emit` fourni à la construction — déjà rendu
thread-safe par la composition root. Implémentations : SttVoiceEngine (réel),
FakeVoiceEngine (démo/tests), demain un sidecar Rust parlant le même contrat.
"""

from __future__ import annotations

from typing import Protocol


class VoiceEngine(Protocol):
    def start(self) -> bool:
        """Démarre l'écoute passive du wake word. False si le micro est KO."""
        ...

    def stop(self) -> None: ...

    def start_capture(self) -> None:
        """Bascule en capture de question (après wake ou activation manuelle)."""
        ...

    def stop_capture(self) -> None:
        """Retour à l'écoute passive."""
        ...

    def set_followup_mode(self, enabled: bool) -> None:
        """En session, « Claude, … » seul suffit (sans le reste de la phrase)."""
        ...
