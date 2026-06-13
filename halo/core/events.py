"""Contrat d'événements entre modules — le langage commun de l'app.

Format FIGÉ et versionné : c'est la couture qui permettra de réécrire un module
(ex. l'audio en Rust, en process séparé) sans toucher au reste. Toute évolution
incompatible incrémente EVENTS_VERSION.

Deux familles :
- Événements : produits par les adapters (audio, IA, UI, timers), consommés par
  la machine à états.
- Effets : produits par la machine à états, exécutés par la composition root.
"""

from __future__ import annotations

from dataclasses import dataclass

from halo.core.models import AudioFaultKind, Command, FailureKind, TimerId

EVENTS_VERSION = 1

# ── Événements : moteur audio → core ─────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class WakeDetected:
    """Mot-clé entendu. `residual_text` : parole déjà transcrite après le mot-clé
    (« Claude aide-moi, quelle heure est-il ? » d'un seul souffle)."""

    residual_text: str = ""


@dataclass(frozen=True, slots=True)
class AmplitudeChanged:
    """Niveau micro lissé, normalisé 0..1, ~30 Hz. Pilote l'orbe en LISTENING."""

    level: float


@dataclass(frozen=True, slots=True)
class SpeechStarted:
    pass


@dataclass(frozen=True, slots=True)
class TranscriptPartial:
    """Transcription provisoire, affichée en dim sous l'orbe façon sous-titre."""

    text: str


@dataclass(frozen=True, slots=True)
class SpeechEnded:
    """Fin de parole (silence > seuil VAD). Déclenche la chorégraphie THINKING
    pendant que la transcription finale se calcule."""


@dataclass(frozen=True, slots=True)
class TranscriptFinal:
    text: str


@dataclass(frozen=True, slots=True)
class AudioFault:
    kind: AudioFaultKind
    detail: str = ""


# ── Événements : client IA → core ────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ResponseStarted:
    pass


@dataclass(frozen=True, slots=True)
class ResponseDelta:
    text: str


@dataclass(frozen=True, slots=True)
class ResponseCompleted:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True, slots=True)
class ResponseFailed:
    kind: FailureKind
    hint: str = ""


# ── Événements : app / utilisateur → core ────────────────────────────────────


@dataclass(frozen=True, slots=True)
class TimerFired:
    timer: TimerId


@dataclass(frozen=True, slots=True)
class UserCommand:
    command: Command


type Event = (
    WakeDetected
    | AmplitudeChanged
    | SpeechStarted
    | TranscriptPartial
    | SpeechEnded
    | TranscriptFinal
    | AudioFault
    | ResponseStarted
    | ResponseDelta
    | ResponseCompleted
    | ResponseFailed
    | TimerFired
    | UserCommand
)

# ── Effets : core → composition root ─────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class BringTerminalToForeground:
    pass


@dataclass(frozen=True, slots=True)
class StartCapture:
    """Démarre la capture de la question. `seed_text` : amorce issue du wake."""

    seed_text: str = ""


@dataclass(frozen=True, slots=True)
class StopCapture:
    pass


@dataclass(frozen=True, slots=True)
class SubmitPrompt:
    prompt: str


@dataclass(frozen=True, slots=True)
class ResubmitLastPrompt:
    """Rejoue la dernière question (action de reprise après erreur)."""


@dataclass(frozen=True, slots=True)
class CancelResponse:
    pass


@dataclass(frozen=True, slots=True)
class StartTimer:
    timer: TimerId


@dataclass(frozen=True, slots=True)
class StopTimer:
    timer: TimerId


@dataclass(frozen=True, slots=True)
class ResetSession:
    pass


type Effect = (
    BringTerminalToForeground
    | StartCapture
    | StopCapture
    | SubmitPrompt
    | ResubmitLastPrompt
    | CancelResponse
    | StartTimer
    | StopTimer
    | ResetSession
)
