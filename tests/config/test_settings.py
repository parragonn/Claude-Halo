"""Persistance TOML : valeurs par défaut, aller-retour, validation tolérante."""

from __future__ import annotations

from pathlib import Path

from halo.config.settings import Settings, load_settings, save_settings


def test_missing_file_yields_defaults(tmp_path: Path) -> None:
    settings = load_settings(tmp_path / "absent.toml")
    assert settings == Settings()


def test_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    settings = Settings()
    settings.ai.model = "claude-sonnet-4-6"
    settings.ai.effort = "high"
    settings.ai.system_prompt = "Réponds en alexandrins."
    settings.voice.sensitivity = 0.75
    settings.voice.silence_timeout_s = 2.5
    settings.voice.lexicon = "Rust, Textual, uv"
    settings.appearance.reduced_motion = True
    settings.appearance.accent = "#06B6D4"
    settings.system.history_enabled = True
    save_settings(settings, path)
    assert load_settings(path) == settings


def test_invalid_values_fall_back_or_clamp(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """
[ai]
effort = "extrême"
max_tokens = 999999

[voice]
sensitivity = 12.0
wake_phrase = "   "

[appearance]
theme = "fuchsia"

[inconnu]
mystere = true
""",
        encoding="utf-8",
    )
    settings = load_settings(path)
    assert settings.ai.effort == "medium"
    assert settings.ai.max_tokens == 64000
    assert settings.voice.sensitivity == 0.95
    assert settings.voice.wake_phrase == "Claude, aide-moi"
    assert settings.appearance.theme == "auto"


def test_corrupt_file_yields_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("ceci n'est ;; pas du TOML", encoding="utf-8")
    assert load_settings(path) == Settings()
