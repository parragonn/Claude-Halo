"""Catalogue des modèles Claude proposés dans le sélecteur.

Liste curatée (identifiants à jour, cache 2026-05), rafraîchissable à chaud via
`client.models.list()` après « tester la connexion » (jalon M4).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelInfo:
    id: str
    label: str
    supports_effort: bool = True


CURATED: tuple[ModelInfo, ...] = (
    ModelInfo("claude-opus-4-8", "Opus 4.8 · le plus capable"),
    ModelInfo("claude-fable-5", "Fable 5 · frontière"),
    ModelInfo("claude-sonnet-4-6", "Sonnet 4.6 · équilibré"),
    ModelInfo("claude-haiku-4-5", "Haiku 4.5 · véloce", supports_effort=False),
)

_dynamic: tuple[ModelInfo, ...] = ()


def update_from_api(models: tuple[ModelInfo, ...]) -> None:
    """Remplace la liste affichée par celle de l'API (après test de connexion)."""
    global _dynamic
    _dynamic = models


def all_models() -> tuple[ModelInfo, ...]:
    return _dynamic if _dynamic else CURATED


def find(model_id: str) -> ModelInfo | None:
    for model in (*_dynamic, *CURATED):
        if model.id == model_id:
            return model
    return None


def choices() -> list[tuple[str, str]]:
    return [(m.id, m.label) for m in all_models()]
