"""Historique opt-in des échanges (JSONL dans le dossier de données de l'OS).

Jamais d'audio, jamais de clé : seulement question/réponse/modèle/horodatage,
et uniquement si l'utilisateur a activé l'historique. `clear` efface tout.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from platformdirs import user_data_path


def default_history_path() -> Path:
    return user_data_path("claude-halo", appauthor=False) / "history.jsonl"


class HistoryStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or default_history_path()

    def append_turn(self, *, question: str, answer: str, model: str) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "ts": datetime.now(UTC).isoformat(timespec="seconds"),
                "question": question,
                "answer": answer,
                "model": model,
            }
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass  # l'historique est un confort : jamais bloquant

    def clear(self) -> bool:
        try:
            if self._path.exists():
                self._path.unlink()
                return True
        except OSError:
            pass
        return False
