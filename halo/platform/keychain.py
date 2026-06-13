"""Clé d'API dans le trousseau de l'OS (Credential Manager / Keychain).

Jamais en clair dans un fichier ni dans les logs. Toute erreur du trousseau est
avalée à la frontière : l'app dégrade proprement (clé « non configurée »).
"""

from __future__ import annotations

import keyring

_SERVICE = "claude-halo"
_USERNAME = "anthropic_api_key"


class KeyringSecretStore:
    def get_api_key(self) -> str | None:
        try:
            value = keyring.get_password(_SERVICE, _USERNAME)
        except Exception:  # trousseau indisponible = clé absente
            return None
        return value or None

    def set_api_key(self, value: str) -> bool:
        try:
            keyring.set_password(_SERVICE, _USERNAME, value.strip())
        except Exception:
            return False
        return True

    def clear_api_key(self) -> bool:
        try:
            keyring.delete_password(_SERVICE, _USERNAME)
        except Exception:
            return False
        return True
