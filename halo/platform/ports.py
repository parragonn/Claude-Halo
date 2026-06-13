"""Ports de l'intégration OS : interfaces abstraites, implémentations ailleurs."""

from __future__ import annotations

from typing import Protocol


class SecretStore(Protocol):
    """Stockage sécurisé de la clé d'API (trousseau de l'OS)."""

    def get_api_key(self) -> str | None: ...

    def set_api_key(self, value: str) -> bool: ...

    def clear_api_key(self) -> bool: ...


class WindowManager(Protocol):
    """Mise au premier plan de la fenêtre du terminal hôte."""

    def bring_to_foreground(self) -> bool: ...
