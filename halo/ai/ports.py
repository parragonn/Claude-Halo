"""Port du fournisseur de réponses.

Implémentations : ClaudeClient (réel, M4), EchoProvider (bouclage M3),
DemoProvider (markdown scripté, M6). Le TTS et les outils (V2) se grefferont
ici sans refonte : le contrat reste « émettre des événements de réponse ».
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from halo.ai.catalog import ModelInfo
from halo.core import events as ev


@dataclass(frozen=True, slots=True)
class ConnectionReport:
    """Résultat du « tester la connexion » : verdict + liste de modèles à jour."""

    ok: bool
    message: str
    models: tuple[ModelInfo, ...] = ()


@dataclass(frozen=True, slots=True)
class PromptRequest:
    messages: tuple[dict[str, str], ...]
    model: str
    effort: str
    system_prompt: str
    language: str
    max_tokens: int


class ResponseProvider(Protocol):
    async def respond(
        self, request: PromptRequest, emit: Callable[[ev.Event], None]
    ) -> None:
        """Émet ResponseStarted, des ResponseDelta puis ResponseCompleted —
        ou ResponseFailed. Annulable via asyncio (CancelledError propre)."""
        ...
