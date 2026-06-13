"""Modèle de configuration typé + chargement/sauvegarde TOML avec validation.

La clé d'API ne vit JAMAIS ici (trousseau de l'OS, voir halo.platform.keychain).
Valeur invalide ou inconnue → valeur par défaut, sans jamais faire échouer le
lancement.
"""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import tomli_w
from platformdirs import user_config_path

from halo.config import defaults as d


def _pick(value: Any, allowed: tuple[str, ...], default: str) -> str:
    return value if isinstance(value, str) and value in allowed else default


def _text(value: Any, default: str) -> str:
    return value if isinstance(value, str) else default


def _clamp(value: Any, low: float, high: float, default: float) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return default
    return max(low, min(high, float(value)))


def _flag(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default


@dataclass(slots=True)
class AiSettings:
    backend: str = d.DEFAULT_BACKEND
    model: str = d.DEFAULT_MODEL
    effort: str = d.DEFAULT_EFFORT
    system_prompt: str = d.DEFAULT_SYSTEM_PROMPT
    language: str = d.DEFAULT_LANGUAGE
    max_tokens: int = d.DEFAULT_MAX_TOKENS

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AiSettings:
        return cls(
            backend=_pick(data.get("backend"), ("api", "claude_code"), d.DEFAULT_BACKEND),
            model=_text(data.get("model"), d.DEFAULT_MODEL) or d.DEFAULT_MODEL,
            effort=_pick(data.get("effort"), ("off", "low", "medium", "high"), d.DEFAULT_EFFORT),
            system_prompt=_text(data.get("system_prompt"), d.DEFAULT_SYSTEM_PROMPT),
            language=_pick(data.get("language"), ("fr", "en", "auto"), d.DEFAULT_LANGUAGE),
            max_tokens=int(_clamp(data.get("max_tokens"), 256, 64000, d.DEFAULT_MAX_TOKENS)),
        )


@dataclass(slots=True)
class VoiceSettings:
    wake_phrase: str = d.DEFAULT_WAKE_PHRASE
    mic_device: str = d.DEFAULT_MIC_DEVICE
    sensitivity: float = d.DEFAULT_SENSITIVITY
    stt_model: str = d.DEFAULT_STT_MODEL
    stt_device: str = d.DEFAULT_STT_DEVICE
    silence_timeout_s: float = d.DEFAULT_SILENCE_TIMEOUT_S
    lexicon: str = d.DEFAULT_LEXICON
    calibrated: bool = d.DEFAULT_CALIBRATED
    noise_floor: float = d.DEFAULT_NOISE_FLOOR
    calibrated_gain: float = d.DEFAULT_CALIBRATED_GAIN

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VoiceSettings:
        wake = _text(data.get("wake_phrase"), d.DEFAULT_WAKE_PHRASE).strip()
        return cls(
            wake_phrase=wake or d.DEFAULT_WAKE_PHRASE,
            mic_device=_text(data.get("mic_device"), d.DEFAULT_MIC_DEVICE)
            or d.DEFAULT_MIC_DEVICE,
            sensitivity=_clamp(data.get("sensitivity"), 0.1, 0.95, d.DEFAULT_SENSITIVITY),
            stt_model=_pick(
                data.get("stt_model"), ("tiny", "small", "medium"), d.DEFAULT_STT_MODEL
            ),
            stt_device=_pick(
                data.get("stt_device"), ("auto", "cuda", "cpu"), d.DEFAULT_STT_DEVICE
            ),
            silence_timeout_s=_clamp(
                data.get("silence_timeout_s"), 1.0, 8.0, d.DEFAULT_SILENCE_TIMEOUT_S
            ),
            lexicon=_text(data.get("lexicon"), d.DEFAULT_LEXICON),
            calibrated=_flag(data.get("calibrated"), d.DEFAULT_CALIBRATED),
            noise_floor=_clamp(data.get("noise_floor"), 0.0, 1.0, d.DEFAULT_NOISE_FLOOR),
            calibrated_gain=_clamp(
                data.get("calibrated_gain"), 1.0, 8.0, d.DEFAULT_CALIBRATED_GAIN
            ),
        )


@dataclass(slots=True)
class AppearanceSettings:
    theme: str = d.DEFAULT_THEME
    accent: str = d.DEFAULT_ACCENT
    reveal: str = d.DEFAULT_REVEAL
    reduced_motion: bool = d.DEFAULT_REDUCED_MOTION
    density: str = d.DEFAULT_DENSITY

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppearanceSettings:
        return cls(
            theme=_pick(data.get("theme"), ("auto", "dark", "light"), d.DEFAULT_THEME),
            accent=_text(data.get("accent"), d.DEFAULT_ACCENT) or d.DEFAULT_ACCENT,
            reveal=_pick(data.get("reveal"), ("fade", "typewriter", "instant"), d.DEFAULT_REVEAL),
            reduced_motion=_flag(data.get("reduced_motion"), d.DEFAULT_REDUCED_MOTION),
            density=_pick(data.get("density"), ("comfortable", "compact"), d.DEFAULT_DENSITY),
        )


@dataclass(slots=True)
class SystemSettings:
    foreground_mode: str = d.DEFAULT_FOREGROUND_MODE
    idle_return_s: float = d.DEFAULT_IDLE_RETURN_S
    autostart: bool = d.DEFAULT_AUTOSTART
    history_enabled: bool = d.DEFAULT_HISTORY_ENABLED

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SystemSettings:
        return cls(
            foreground_mode=_pick(
                data.get("foreground_mode"), ("always", "unfocused"), d.DEFAULT_FOREGROUND_MODE
            ),
            idle_return_s=_clamp(data.get("idle_return_s"), 30.0, 3600.0, d.DEFAULT_IDLE_RETURN_S),
            autostart=_flag(data.get("autostart"), d.DEFAULT_AUTOSTART),
            history_enabled=_flag(data.get("history_enabled"), d.DEFAULT_HISTORY_ENABLED),
        )


@dataclass(slots=True)
class Settings:
    ai: AiSettings = field(default_factory=AiSettings)
    voice: VoiceSettings = field(default_factory=VoiceSettings)
    appearance: AppearanceSettings = field(default_factory=AppearanceSettings)
    system: SystemSettings = field(default_factory=SystemSettings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ai": asdict(self.ai),
            "voice": asdict(self.voice),
            "appearance": asdict(self.appearance),
            "system": asdict(self.system),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Settings:
        def section(name: str) -> dict[str, Any]:
            value = data.get(name)
            return value if isinstance(value, dict) else {}

        return cls(
            ai=AiSettings.from_dict(section("ai")),
            voice=VoiceSettings.from_dict(section("voice")),
            appearance=AppearanceSettings.from_dict(section("appearance")),
            system=SystemSettings.from_dict(section("system")),
        )


def config_path() -> Path:
    return user_config_path("claude-halo", appauthor=False) / "config.toml"


def load_settings(path: Path | None = None) -> Settings:
    path = path or config_path()
    try:
        with path.open("rb") as handle:
            return Settings.from_dict(tomllib.load(handle))
    except FileNotFoundError:
        return Settings()
    except (OSError, tomllib.TOMLDecodeError):
        return Settings()


def save_settings(settings: Settings, path: Path | None = None) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        tomli_w.dump(settings.to_dict(), handle)
