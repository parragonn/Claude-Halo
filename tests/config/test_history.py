"""Historique opt-in : JSONL append + effacement."""

from __future__ import annotations

import json
from pathlib import Path

from halo.config.history import HistoryStore


def test_append_then_clear(tmp_path: Path) -> None:
    path = tmp_path / "data" / "history.jsonl"
    store = HistoryStore(path)
    store.append_turn(question="quelle heure ?", answer="**Il est tard.**", model="claude-opus-4-8")
    store.append_turn(question="merci", answer="De rien.", model="claude-opus-4-8")

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["question"] == "quelle heure ?"
    assert first["model"] == "claude-opus-4-8"
    assert "ts" in first

    assert store.clear() is True
    assert not path.exists()
    assert store.clear() is False
