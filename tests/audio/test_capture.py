"""Niveau RMS, VAD énergie, anneaux de blocs — sans matériel audio."""

from __future__ import annotations

import numpy as np

from halo.audio.capture import (
    BLOCK_SAMPLES,
    BLOCK_SECONDS,
    SAMPLE_RATE,
    BlockRing,
    EnergyVad,
    block_rms,
    rms_to_level,
)


def block(value: float) -> np.ndarray:
    return np.full(BLOCK_SAMPLES, value, dtype=np.float32)


def test_rms_and_level_mapping() -> None:
    assert block_rms(block(0.0)) == 0.0
    assert rms_to_level(0.0) == 0.0
    assert rms_to_level(0.5) == 1.0
    assert 0.0 < rms_to_level(0.01) < rms_to_level(0.05) < 1.0


def test_vad_attack_after_three_voiced_blocks() -> None:
    vad = EnergyVad(0.6)
    vad.update(0.05)
    vad.update(0.05)
    assert not vad.speaking
    vad.update(0.05)
    assert vad.speaking
    assert vad.silence_for == 0.0


def test_vad_hangover_survives_short_dips() -> None:
    vad = EnergyVad(0.6)
    for _ in range(3):
        vad.update(0.05)
    for _ in range(6):  # ~0,19 s de creux < relâche 0,30 s
        vad.update(0.0005)
    assert vad.speaking
    vad.update(0.05)
    assert vad.speaking
    assert vad.silence_for == 0.0


def test_vad_releases_then_counts_silence() -> None:
    vad = EnergyVad(0.6)
    for _ in range(3):
        vad.update(0.05)
    for _ in range(12):  # ~0,38 s > relâche
        vad.update(0.0005)
    assert not vad.speaking
    assert vad.silence_for > 0.35


def test_noise_floor_adapts_to_sustained_hum() -> None:
    vad = EnergyVad(0.6)
    initial = vad.noise_floor
    for _ in range(150):  # ~4,8 s de ronronnement constant
        vad.update(0.010)
    assert vad.noise_floor > initial * 1.8
    assert not vad.speaking


def test_resample_preserves_duration_and_pitch() -> None:
    from halo.audio.capture import resample_to_16k

    seconds = 0.5
    source_rate = 48_000
    t = np.arange(int(source_rate * seconds)) / source_rate
    sine = np.sin(2 * np.pi * 440.0 * t).astype(np.float32)
    out = resample_to_16k(sine, source_rate)
    assert abs(out.size - SAMPLE_RATE * seconds) <= 2
    crossings = int(np.sum(np.diff(np.signbit(out)) != 0))
    assert abs(crossings - 440 * 2 * seconds) <= 6  # ~880 passages à zéro pour 0,5 s


def test_is_virtual_device_flags_mixers() -> None:
    from halo.audio.capture import is_virtual_device

    assert is_virtual_device("Voicemeeter Out B2 (VB-Audio)")
    assert is_virtual_device("CABLE Output (VB-Audio Virtual Cable)")
    assert is_virtual_device("Mixage stéréo (Realtek)")
    assert not is_virtual_device("Microphone (Scarlett Solo 4th Gen)")
    assert not is_virtual_device("Microphone (NVIDIA Broadcast)")


def test_real_microphone_excludes_virtual_and_mappers() -> None:
    from halo.audio.capture import _is_real_microphone

    assert _is_real_microphone("Microphone (Scarlett Solo 4th Gen)")
    assert _is_real_microphone("Microphone (NVIDIA Broadcast)")
    assert not _is_real_microphone("Voicemeeter Out B2 (VB-Audio)")
    assert not _is_real_microphone("Mappeur de sons Microsoft - Input")
    assert not _is_real_microphone("Pilote de capture audio principal")
    assert not _is_real_microphone("")


def test_resample_attenuates_aliasing_frequencies() -> None:
    from halo.audio.capture import resample_to_16k

    # Un ton à 15 kHz (au-dessus de la Nyquist cible de 8 kHz) doit être filtré,
    # pas replié en parasite audible dans la bande de la voix.
    source_rate = 44_100
    t = np.arange(int(source_rate * 0.5)) / source_rate
    tone = np.sin(2 * np.pi * 15_000.0 * t).astype(np.float32)
    out = resample_to_16k(tone, source_rate)
    assert float(np.abs(out).max()) < 0.2  # fortement atténué

    # Un ton vocal à 300 Hz passe quasi intact.
    voice = np.sin(2 * np.pi * 300.0 * t).astype(np.float32)
    out_voice = resample_to_16k(voice, source_rate)
    assert float(np.abs(out_voice).max()) > 0.7


def test_rate_adapter_rechunks_with_carry() -> None:
    from halo.audio.capture import RateAdapter

    adapter = RateAdapter(48_000)
    total = 0
    for _ in range(10):  # 10 blocs natifs de 1536 éch. = 0,32 s
        blocks = adapter.feed(np.zeros(1536, dtype=np.float32))
        assert all(b.size == BLOCK_SAMPLES for b in blocks)
        total += sum(b.size for b in blocks)
    assert abs(total - 0.32 * SAMPLE_RATE) <= BLOCK_SAMPLES


def test_merged_lexicon_prepends_user_terms_and_caps_length() -> None:
    from halo.audio.stt import merged_lexicon

    base = merged_lexicon()
    assert "Rust" in base and "API" in base
    custom = merged_lexicon("Textual, uv,   mypy")
    assert custom.startswith("Textual, uv, mypy")
    assert "Rust" in custom
    assert len(merged_lexicon("x" * 1000)) <= 400


def test_normalize_audio_boosts_quiet_keeps_loud() -> None:
    from halo.audio.stt import normalize_audio

    quiet = np.full(1000, 0.05, dtype=np.float32)
    boosted = normalize_audio(quiet)
    assert 0.85 <= float(np.abs(boosted).max()) <= 0.95

    loud = np.full(1000, 0.6, dtype=np.float32)
    assert normalize_audio(loud) is loud

    silence = np.zeros(1000, dtype=np.float32)
    assert normalize_audio(silence) is silence


def test_block_ring_caps_duration_and_tail() -> None:
    ring = BlockRing(max_seconds=3 * BLOCK_SECONDS)
    for value in (0.1, 0.2, 0.3, 0.4, 0.5):
        ring.append(block(value))
    data = ring.concat()
    assert data.size == 3 * BLOCK_SAMPLES
    assert data[0] == np.float32(0.3)  # les plus anciens sont sortis
    tail = ring.tail(BLOCK_SECONDS)
    assert tail.size == BLOCK_SAMPLES
    assert tail[0] == np.float32(0.5)
