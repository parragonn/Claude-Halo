"""Logique pure de calibration : SNR→sensibilité, voix→gain, verdict."""

from __future__ import annotations

from halo.audio.calibration import (
    calibrate,
    gain_from_voice,
    sensitivity_from_snr,
)


def test_sensitivity_decreases_with_clean_signal() -> None:
    # Micro propre (SNR élevé) → seuil haut → peu sensible (ignore le bruit).
    clean = sensitivity_from_snr(100.0)
    noisy = sensitivity_from_snr(3.0)
    assert clean < noisy
    assert 0.1 <= clean <= 0.95
    assert 0.1 <= noisy <= 0.95


def test_sensitivity_bounds() -> None:
    assert sensitivity_from_snr(1.0) == 0.95  # bruyant → max sensible
    assert sensitivity_from_snr(10_000.0) == 0.1  # ultra propre → min sensible


def test_gain_boosts_quiet_voice() -> None:
    assert gain_from_voice(0.01) > 1.0
    assert gain_from_voice(0.2) == 1.0  # déjà fort → pas de gain
    assert gain_from_voice(0.0) == 1.0  # silence → neutre
    assert gain_from_voice(0.0001) <= 8.0  # borné


def test_calibrate_excellent_mic() -> None:
    result = calibrate(noise_rms=0.001, voice_rms=0.05)
    assert result.snr == 50.0
    assert result.quality == "excellent"
    assert result.gain > 1.0
    assert result.sensitivity < 0.5


def test_calibrate_noisy_environment() -> None:
    result = calibrate(noise_rms=0.04, voice_rms=0.05)
    assert result.snr < 2.0
    assert result.quality == "faible"
    assert "bruit" in result.message.lower()


def test_calibrate_weak_voice_flagged() -> None:
    result = calibrate(noise_rms=0.0005, voice_rms=0.004)
    assert result.quality == "faible"
    assert "faible" in result.message.lower()


def test_calibrate_good_mic_mid_snr() -> None:
    result = calibrate(noise_rms=0.005, voice_rms=0.04)
    assert result.quality in ("bon", "moyen")
    assert 0.1 <= result.sensitivity <= 0.95


def test_summarize_percentile() -> None:
    from halo.audio.mic_calibrator import _summarize

    assert _summarize([], percentile=75) == 0.0
    # p75 d'une rampe : capture les niveaux hauts (moments parlés).
    values = [0.01, 0.02, 0.03, 0.08, 0.09, 0.10]
    assert _summarize(values, percentile=75) > 0.07
