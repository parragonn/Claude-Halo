"""Types du domaine — purs, sans dépendance, immuables quand c'est possible."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class Phase(Enum):
    """Phase visible de l'application (machine à états du spec §4.1)."""

    IDLE = auto()
    LISTENING = auto()
    THINKING = auto()
    RESPONDING = auto()
    SESSION_IDLE = auto()


@dataclass(frozen=True, slots=True)
class MachineState:
    """État complet de la machine ; `in_session` distingue la 1re question des suivantes
    (orbe centrée vs parquée à gauche)."""

    phase: Phase = Phase.IDLE
    in_session: bool = False


class FailureKind(Enum):
    """Taxonomie des échecs d'appel au modèle, affichés calmement dans l'UI."""

    AUTH = auto()
    BILLING = auto()
    OFFLINE = auto()
    RATE_LIMIT = auto()
    OVERLOADED = auto()
    TIMEOUT = auto()
    BAD_REQUEST = auto()
    UNKNOWN = auto()


class AudioFaultKind(Enum):
    NO_MIC = auto()
    PERMISSION_DENIED = auto()
    DEVICE_LOST = auto()
    ENGINE_ERROR = auto()


class TimerId(Enum):
    SESSION_IDLE_TIMEOUT = auto()


class Command(Enum):
    """Actions utilisateur de haut niveau (clavier ou boutons)."""

    MANUAL_WAKE = auto()
    NEW_SESSION = auto()
    BACK_HOME = auto()
    CANCEL = auto()
    RETRY = auto()


@dataclass(slots=True)
class Turn:
    """Un tour de conversation : question orale -> réponse écrite (streamée)."""

    question: str
    answer: str = ""
    error: FailureKind | None = None
    error_hint: str = ""
    completed: bool = False
