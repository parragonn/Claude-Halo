"""Orchestrateur de calibration micro (audio I/O), piloté par l'assistant UI.

Mesure le bruit ambiant (silence) puis la voix de l'utilisateur, en réutilisant
MicSource (donc 16 kHz de qualité). Transcrit la phrase test avec le gain
calibré pour montrer un résultat concret. Tout se passe dans un thread ; la
progression remonte par callbacks (l'UI fait call_from_thread).
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from time import monotonic

import numpy as np

from halo.audio.calibration import CalibrationResult, calibrate
from halo.audio.capture import MicSource, block_rms, rms_to_level
from halo.audio.stt import ModelStore, Transcriber, merged_lexicon
from halo.config.settings import Settings

NOISE_SECONDS = 2.0
VOICE_SECONDS = 4.0
_TRANSCRIBE_TIMEOUT_S = 30.0  # garde-fou : jamais bloqué sur « Analyse… »

type PhaseFn = Callable[[str], None]
type LevelFn = Callable[[float], None]
type DoneFn = Callable[[CalibrationResult, str], None]
type ErrorFn = Callable[[str], None]


def _summarize(rms_values: list[float], *, percentile: float) -> float:
    if not rms_values:
        return 0.0
    return float(np.percentile(np.array(rms_values), percentile))


class MicCalibrator:
    def __init__(self, settings: Settings, store: ModelStore) -> None:
        self._settings = settings
        self._transcriber = Transcriber(store)

    def run(
        self,
        *,
        on_phase: PhaseFn,
        on_level: LevelFn,
        on_done: DoneFn,
        on_error: ErrorFn,
    ) -> None:
        """Pipeline complet (bloquant — à lancer dans un thread)."""
        try:
            # Pré-charge le modèle AVANT de mesurer : le premier chargement
            # (medium/CUDA) peut prendre plusieurs secondes — autant que ce soit
            # une étape « Préparation… » explicite, et que la transcription
            # finale soit instantanée plutôt qu'un « Analyse… » qui traîne.
            on_phase("prepare")
            self._transcriber.warm_up(self._settings.voice.stt_model)

            on_phase("noise")
            _audio_noise, noise_rms_values = self._record(NOISE_SECONDS, on_level=None)
            noise_rms = _summarize(noise_rms_values, percentile=60)

            on_phase("voice")
            audio_voice, voice_rms_values = self._record(VOICE_SECONDS, on_level=on_level)
            voice_rms = _summarize(voice_rms_values, percentile=75)

            result = calibrate(noise_rms, voice_rms)

            on_phase("transcribe")
            transcript = self._transcribe_with_timeout(audio_voice, result.gain)
            on_done(result, transcript)
        except TimeoutError:
            on_error("la transcription a pris trop de temps — réessaie")
        except Exception as exc:  # toute panne micro → message propre, jamais de trace
            on_error(str(exc)[:160])

    def _transcribe_with_timeout(self, audio: np.ndarray, gain: float) -> str:
        """Transcription bornée dans le temps : si le moteur STT se fige (cas
        limite GPU/threads), on rend la main plutôt que de bloquer l'assistant."""
        box: dict[str, str] = {}
        error: list[BaseException] = []

        def work() -> None:
            try:
                box["text"] = self._transcriber.transcribe(
                    audio,
                    size=self._settings.voice.stt_model,
                    language=self._language(),
                    quality=True,
                    bias=self._settings.voice.wake_phrase,
                    lexicon=merged_lexicon(self._settings.voice.lexicon),
                    gain=gain,
                )
            except BaseException as exc:
                error.append(exc)

        worker = threading.Thread(target=work, name="halo-calib-stt", daemon=True)
        worker.start()
        worker.join(timeout=_TRANSCRIBE_TIMEOUT_S)
        if worker.is_alive():
            raise TimeoutError
        if error:
            raise RuntimeError(str(error[0])[:160])
        return box.get("text", "")

    def _language(self) -> str | None:
        language = self._settings.ai.language
        return language if language in ("fr", "en") else None

    def _record(
        self, duration: float, on_level: LevelFn | None
    ) -> tuple[np.ndarray, list[float]]:
        blocks_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=128)
        mic = MicSource(self._settings.voice.mic_device, blocks_queue)
        mic.start()
        blocks: list[np.ndarray] = []
        rms_values: list[float] = []
        deadline = monotonic() + duration
        try:
            while monotonic() < deadline:
                try:
                    block = blocks_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                blocks.append(block)
                rms = block_rms(block)
                rms_values.append(rms)
                if on_level is not None:
                    on_level(rms_to_level(rms))
        finally:
            mic.stop()
        audio = np.concatenate(blocks) if blocks else np.zeros(0, dtype=np.float32)
        return audio, rms_values
