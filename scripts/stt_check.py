"""Diagnostic STT : enregistre quelques secondes et montre ce que Whisper entend.

Usage :
  uv run python scripts/stt_check.py                 # micro par défaut, modèle config
  uv run python scripts/stt_check.py --list          # liste les micros (avec index)
  uv run python scripts/stt_check.py --device 3      # force un périphérique
  uv run python scripts/stt_check.py --seconds 6 --models small,medium

Sur GPU, lance avec « uv run --extra cuda python scripts/stt_check.py ».
Affiche le device audio, son taux, les niveaux, et la transcription pour chaque
modèle demandé. Rien n'est écrit sur disque.
"""

from __future__ import annotations

import argparse
import sys
import time

import numpy as np

from halo.audio.capture import SAMPLE_RATE, RateAdapter, block_rms, is_virtual_device
from halo.audio.stt import ModelStore, Transcriber, merged_lexicon
from halo.config.settings import load_settings


def list_devices() -> None:
    import sounddevice as sd

    default_in = sd.default.device[0]
    print("Périphériques d'entrée :")
    for index, info in enumerate(sd.query_devices()):
        if info.get("max_input_channels", 0) <= 0:
            continue
        name = str(info.get("name", ""))
        flags = " ← défaut" if index == default_in else ""
        if is_virtual_device(name):
            flags += "  ⚠ périphérique VIRTUEL (préfère ton vrai micro physique)"
        print(f"  [{index:>2}] {name}  ({info.get('default_samplerate', 0):.0f} Hz){flags}")


def record(seconds: float, device: int | None) -> tuple[np.ndarray, str, float]:
    import sounddevice as sd

    info = sd.query_devices(device, kind="input")
    native = float(info.get("default_samplerate") or SAMPLE_RATE)
    name = str(info.get("name", "?"))
    print(f"\nPériphérique : [{device if device is not None else 'défaut'}] {name}")
    if is_virtual_device(name):
        print("  ⚠ Ce périphérique est VIRTUEL (Voicemeeter / VB-Audio / mixage).")
        print("    Le son y est traité/remixé — choisis ton micro physique avec --device.")
    print(f"  taux natif {native:.0f} Hz")
    print(f"\nParle pendant {seconds:.0f} s… (ex. « Claude, aide-moi, comment apprendre Rust ? »)")
    recording = sd.rec(int(seconds * native), samplerate=native, channels=1, dtype="float32")
    sd.wait()
    blocks = RateAdapter(native).feed(recording[:, 0])
    audio = np.concatenate(blocks) if blocks else np.zeros(0, dtype=np.float32)
    return audio, name, native


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    settings = load_settings()
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true", help="liste les micros puis quitte")
    parser.add_argument("--device", type=int, default=None, help="index du périphérique d'entrée")
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--models", default=settings.voice.stt_model, help="ex. small,medium")
    args = parser.parse_args()

    if args.list:
        list_devices()
        return

    language = settings.ai.language if settings.ai.language in ("fr", "en") else None
    sizes = [m.strip() for m in args.models.split(",") if m.strip()]
    audio, _name, _native = record(args.seconds, args.device)

    peak = float(np.abs(audio).max()) if audio.size else 0.0
    rms = block_rms(audio)
    print(f"\nNiveaux      : pic {peak:.3f} · RMS {rms:.4f}", end="")
    if peak < 0.05:
        print("  ⚠ très faible — rapproche-toi ou monte le gain")
    elif peak > 0.99:
        print("  ⚠ saturation — éloigne-toi ou baisse le gain")
    else:
        print("  ✓ exploitable")

    store = ModelStore(lambda: settings.voice.stt_device)
    transcriber = Transcriber(store)
    lexicon = merged_lexicon(settings.voice.lexicon)
    print(f"\nLangue {language or 'auto'} · device {store.active_device} · transcriptions :")
    for size in sizes:
        started = time.perf_counter()
        text = transcriber.transcribe(
            audio,
            size=size,
            language=language,
            quality=True,
            bias=settings.voice.wake_phrase,
            lexicon=lexicon,
        )
        elapsed = time.perf_counter() - started
        print(f"  [{size:<7}] {elapsed:5.1f}s  → {text!r}")
    if store.cuda_error:
        print(f"\n(CUDA indisponible : {store.cuda_error})")


if __name__ == "__main__":
    main()
