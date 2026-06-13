"""Calibration micro — logique pure : (bruit, voix) → réglages adaptés.

À partir du RMS du bruit ambiant et du RMS de la voix de l'utilisateur, on
dérive la sensibilité VAD, un gain de normalisation et un verdict qualité.
Zéro I/O, zéro dépendance : entièrement testable. L'orchestration (ouverture
micro, fenêtres de mesure, transcription) vit dans `mic_calibrator.py`.

Le seuil VAD vaut `noise_floor × k` avec `k = 2.2 + 5.3·(1−sensibilité)`
(cf. EnergyVad). On vise un seuil au point géométrique entre bruit et voix,
soit `k = √SNR` — un micro propre (SNR élevé) donne un seuil haut (peu sensible,
ignore le bruit) ; un micro bruyant pousse la sensibilité au max et avertit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

TARGET_VOICE_RMS = 0.07  # niveau de voix confortable visé après gain
_K_BASE = 2.2
_K_SPAN = 5.3
_K_MAX = _K_BASE + _K_SPAN  # 7.5 — borne haute du multiplicateur VAD
_MAX_GAIN = 8.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def sensitivity_from_snr(snr: float) -> float:
    """SNR mesuré → sensibilité VAD 0.1..0.95 (consommée par VoiceSettings)."""
    k = _clamp(math.sqrt(max(snr, 1.0)), _K_BASE, _K_MAX)
    sensitivity = 1.0 - (k - _K_BASE) / _K_SPAN
    return round(_clamp(sensitivity, 0.1, 0.95), 2)


def gain_from_voice(voice_rms: float) -> float:
    """Niveau de voix → gain pour l'amener à la cible (1.0 si déjà suffisant)."""
    if voice_rms <= 1e-5:
        return 1.0
    return round(_clamp(TARGET_VOICE_RMS / voice_rms, 1.0, _MAX_GAIN), 2)


@dataclass(frozen=True, slots=True)
class CalibrationResult:
    noise_rms: float
    voice_rms: float
    snr: float
    sensitivity: float
    gain: float
    quality: str  # excellent | bon | moyen | faible
    message: str


def _verdict(snr: float, voice_rms: float) -> tuple[str, str]:
    if voice_rms < 0.008:
        return "faible", "Voix très faible — rapproche-toi du micro ou monte son gain."
    if snr < 2.0:
        return "faible", "Beaucoup de bruit de fond — un environnement plus calme aiderait."
    if snr < 4.0:
        return "moyen", "Correct. Un endroit plus calme améliorerait encore la précision."
    if snr < 10.0:
        return "bon", "Bon micro, bien au-dessus du bruit ambiant."
    return "excellent", "Micro excellent, signal très propre."


def calibrate(noise_rms: float, voice_rms: float) -> CalibrationResult:
    noise = max(noise_rms, 0.0)
    voice = max(voice_rms, 0.0)
    snr = voice / max(noise, 1e-5)
    quality, message = _verdict(snr, voice)
    return CalibrationResult(
        noise_rms=noise,
        voice_rms=voice,
        snr=snr,
        sensitivity=sensitivity_from_snr(snr),
        gain=gain_from_voice(voice),
        quality=quality,
        message=message,
    )
