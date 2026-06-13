"""Le contrat d'événements est figé : version explicite, types immuables."""

from __future__ import annotations

import dataclasses

import pytest

from halo.core import events as ev


def test_contract_version() -> None:
    assert ev.EVENTS_VERSION == 1


def test_events_are_frozen() -> None:
    event = ev.TranscriptFinal(text="bonjour")
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.text = "autre"  # type: ignore[misc]


def test_effects_are_frozen() -> None:
    effect = ev.SubmitPrompt(prompt="question")
    with pytest.raises(dataclasses.FrozenInstanceError):
        effect.prompt = "autre"  # type: ignore[misc]
