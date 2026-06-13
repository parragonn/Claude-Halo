"""Capture micro : niveau RMS, VAD énergie à hystérésis, anneaux d'audio.

Les parties pures (niveau, VAD, anneau) sont testées sans matériel. L'accès
PortAudio (sounddevice) est isolé dans MicSource / list_microphones, avec
imports paresseux pour que le reste fonctionne sans la DLL.
"""

from __future__ import annotations

import math
import queue
from collections import deque
from collections.abc import Callable
from typing import Any

import numpy as np

from halo.core.models import AudioFaultKind

SAMPLE_RATE = 16_000
BLOCK_SAMPLES = 512
BLOCK_SECONDS = BLOCK_SAMPLES / SAMPLE_RATE


def _lowpass_kernel(cutoff_hz: float, source_rate: float, taps: int = 65) -> np.ndarray:
    """Noyau FIR passe-bas (sinc fenêtré Hamming) — anti-repliement avant
    décimation. Sans lui, un downsampling replie les aigus en parasites dans
    la bande de la voix (« mots proches mais faux »)."""
    nyq = source_rate / 2.0
    fc = min(cutoff_hz, 0.95 * nyq) / nyq  # coupure normalisée 0..1
    n = np.arange(taps) - (taps - 1) / 2.0
    sinc = np.sinc(fc * n) * fc
    window = np.hamming(taps)
    kernel = sinc * window
    normalized: np.ndarray = (kernel / kernel.sum()).astype(np.float32)
    return normalized


def resample_to_16k(samples: np.ndarray, source_rate: float) -> np.ndarray:
    """Rééchantillonnage vers 16 kHz avec filtre anti-repliement à la décimation.

    Repli uniquement : en marche normale, PortAudio/WASAPI fournit déjà du 16 kHz
    de qualité. Conçu pour un signal d'un bloc (cas streaming) ou complet (banc)."""
    if samples.size == 0 or source_rate == SAMPLE_RATE:
        return np.asarray(samples, dtype=np.float32)
    work = np.asarray(samples, dtype=np.float32)
    if source_rate > SAMPLE_RATE:  # downsampling : filtrer d'abord
        kernel = _lowpass_kernel(SAMPLE_RATE * 0.45, source_rate)
        work = np.convolve(work, kernel, mode="same")
    target = max(1, round(work.size * SAMPLE_RATE / source_rate))
    positions = np.linspace(0.0, work.size - 1, target)
    resampled = np.interp(positions, np.arange(work.size), work)
    return np.asarray(resampled, dtype=np.float32)


class RateAdapter:
    """Blocs au taux natif du périphérique → blocs fixes de 512 éch. à 16 kHz."""

    def __init__(self, source_rate: float) -> None:
        self.source_rate = float(source_rate)
        self._carry = np.zeros(0, dtype=np.float32)

    def feed(self, native_block: np.ndarray) -> list[np.ndarray]:
        converted = resample_to_16k(native_block, self.source_rate)
        data = np.concatenate([self._carry, converted]) if self._carry.size else converted
        blocks: list[np.ndarray] = []
        index = 0
        while data.size - index >= BLOCK_SAMPLES:
            blocks.append(data[index : index + BLOCK_SAMPLES])
            index += BLOCK_SAMPLES
        self._carry = data[index:].copy()
        return blocks


def block_rms(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    value: float = float(np.sqrt(np.mean(np.square(samples), dtype=np.float64)))
    return value


def rms_to_level(rms: float) -> float:
    """RMS micro → niveau 0..1 vif et lisible pour l'orbe."""
    if rms <= 0.0:
        return 0.0
    return float(min(1.0, (rms * 16.0) ** 0.7))


class EnergyVad:
    """Détection de parole par énergie : plancher de bruit adaptatif + hystérésis.

    - `speaking` : vrai pendant la parole (attaque sur 3 blocs, relâche ~0,3 s) ;
    - `silence_for` : secondes écoulées depuis le dernier bloc voisé — c'est le
      moteur qui la compare au seuil de fin de question (configurable).
    """

    def __init__(
        self,
        sensitivity: float = 0.6,
        *,
        noise_floor: float = 0.0,
        abs_floor: float = 0.0035,
        attack_blocks: int = 3,
        hangover_s: float = 0.30,
        floor_tau_s: float = 2.5,
    ) -> None:
        # Sensibilité 0,1..0,95 → multiplicateur de seuil 7,5 (sourd) .. 2,2 (sensible).
        self._k = 2.2 + 5.3 * (1.0 - max(0.1, min(0.95, sensitivity)))
        self._abs_floor = abs_floor
        self._attack_blocks = attack_blocks
        self._hangover_s = hangover_s
        self._floor_tau_s = floor_tau_s
        # Plancher calibré si fourni (>0), sinon départ générique qui s'adapte.
        self.noise_floor = noise_floor if noise_floor > 0.0 else 0.004
        self.speaking = False
        self.silence_for = 0.0
        self._above = 0

    @property
    def threshold(self) -> float:
        return max(self._abs_floor, self.noise_floor * self._k)

    def start_utterance(self) -> None:
        self.silence_for = 0.0

    def update(self, rms: float, dt: float = BLOCK_SECONDS) -> None:
        threshold = self.threshold
        voiced = rms > (threshold * 0.6 if self.speaking else threshold)
        if voiced:
            self._above += 1
            if not self.speaking and self._above >= self._attack_blocks:
                self.speaking = True
            if self.speaking:
                self.silence_for = 0.0
        else:
            self._above = 0
            self.silence_for += dt
            if self.speaking and self.silence_for > self._hangover_s:
                self.speaking = False
        if not self.speaking and self.silence_for > 0.6 and rms < threshold:
            self.noise_floor += (rms - self.noise_floor) * (
                1.0 - math.exp(-dt / self._floor_tau_s)
            )


class BlockRing:
    """Anneau de blocs audio borné en durée (fenêtre wake, pré-roll)."""

    def __init__(self, max_seconds: float) -> None:
        self._max_blocks = max(1, round(max_seconds / BLOCK_SECONDS))
        self._blocks: deque[np.ndarray] = deque(maxlen=self._max_blocks)

    def append(self, block: np.ndarray) -> None:
        self._blocks.append(block)

    def clear(self) -> None:
        self._blocks.clear()

    @property
    def seconds(self) -> float:
        return len(self._blocks) * BLOCK_SECONDS

    def concat(self) -> np.ndarray:
        if not self._blocks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(list(self._blocks))

    def tail(self, seconds: float) -> np.ndarray:
        count = max(0, round(seconds / BLOCK_SECONDS))
        blocks = list(self._blocks)[-count:] if count else []
        if not blocks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(blocks)


class MicError(RuntimeError):
    def __init__(self, kind: AudioFaultKind, detail: str = "") -> None:
        super().__init__(detail)
        self.kind = kind
        self.detail = detail


class MicSource:
    """Flux d'entrée PortAudio → file de blocs float32 mono 16 kHz.

    On demande 16 kHz directement à PortAudio : WASAPI (mode partagé) fait alors
    un rééchantillonnage de qualité, avec anti-repliement — supérieur à tout
    rééchantillonnage maison. Repli au taux natif + filtre FIR si un pilote
    refuse 16 kHz (rare : WDM-KS, mode exclusif).
    """

    def __init__(
        self,
        device: str,
        out: queue.Queue[np.ndarray],
        on_lost: Callable[[], None] | None = None,
    ) -> None:
        self._device = device
        self._out = out
        self._on_lost = on_lost
        self._stream: Any = None
        self._adapter: RateAdapter | None = None
        self._stopping = False

    def start(self) -> None:
        import sounddevice as sd

        self._stopping = False
        index = _resolve_device(self._device)
        try:  # 1. idéal : 16 kHz natif via le rééchantillonneur du pilote
            self._adapter = None
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                blocksize=BLOCK_SAMPLES,
                channels=1,
                dtype="float32",
                device=index,
                callback=self._callback,
                finished_callback=self._finished,
            )
            self._stream.start()
            return
        except Exception:
            self._stream = None  # pilote récalcitrant : on tente le repli filtré

        try:  # 2. repli : taux natif + filtre anti-repliement maison
            native_rate = _native_samplerate(index)
            self._adapter = RateAdapter(native_rate)
            self._stream = sd.InputStream(
                samplerate=native_rate,
                blocksize=max(1, round(native_rate * BLOCK_SECONDS)),
                channels=1,
                dtype="float32",
                device=index,
                callback=self._callback,
                finished_callback=self._finished,
            )
            self._stream.start()
        except Exception as exc:
            self._stream = None
            kind = AudioFaultKind.NO_MIC if _input_device_count() == 0 else (
                AudioFaultKind.ENGINE_ERROR
            )
            raise MicError(kind, str(exc)[:120]) from exc

    def stop(self) -> None:
        self._stopping = True
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass

    def _callback(self, indata: np.ndarray, frames: int, time: object, status: object) -> None:
        adapter = self._adapter
        if adapter is None:  # flux déjà en 16 kHz : pas de rééchantillonnage
            try:
                self._out.put_nowait(indata[:, 0].copy())
            except queue.Full:
                pass
            return
        for block in adapter.feed(indata[:, 0]):
            try:
                self._out.put_nowait(block)
            except queue.Full:
                pass  # mieux vaut perdre un bloc que bloquer le thread PortAudio

    def _finished(self) -> None:
        if not self._stopping and self._on_lost is not None:
            self._on_lost()


def _resolve_device(name: str) -> int | None:
    if name in ("", "default"):
        return None
    try:
        import sounddevice as sd

        for index, info in enumerate(sd.query_devices()):
            if info.get("max_input_channels", 0) > 0 and info.get("name") == name:
                return index
    except Exception:
        pass
    return None


def _native_samplerate(index: int | None) -> float:
    try:
        import sounddevice as sd

        info = sd.query_devices(index, kind="input")
        rate = float(info.get("default_samplerate") or SAMPLE_RATE)
        return rate if rate > 0 else float(SAMPLE_RATE)
    except Exception:
        return float(SAMPLE_RATE)


def _input_device_count() -> int:
    try:
        import sounddevice as sd

        return sum(1 for d in sd.query_devices() if d.get("max_input_channels", 0) > 0)
    except Exception:
        return 0


# Périphériques d'entrée « virtuels » : mixeurs/loopback (Voicemeeter, VB-Audio,
# CABLE, mixage stéréo…). Le son y est traité/remixé — mauvais pour la STT.
_VIRTUAL_MIC_HINTS = (
    "voicemeeter",
    "vb-audio",
    "vb audio",
    "cable",
    "virtual",
    "stereo mix",
    "mixage",
    "loopback",
)


def is_virtual_device(name: str) -> bool:
    lowered = name.lower()
    return any(hint in lowered for hint in _VIRTUAL_MIC_HINTS)


# Pseudo-périphériques de routage (pas un vrai micro) : ils pointent vers le
# défaut système, donc les choisir ne résout pas le problème Voicemeeter.
_MAPPER_HINTS = ("mappeur", "mapper", "pilote de capture", "primary capture", "principal")


def _is_real_microphone(name: str) -> bool:
    lowered = name.lower()
    if is_virtual_device(name) or any(h in lowered for h in _MAPPER_HINTS):
        return False
    return bool(name)


def best_input_device() -> str:
    """Meilleur micro à utiliser par défaut : respecte le défaut système s'il
    est un vrai micro, sinon choisit un périphérique physique nommé « micro… »
    (évite Voicemeeter, CABLE, mappeurs de son…). Retourne « default » ou un nom."""
    try:
        import sounddevice as sd

        devices = sd.query_devices()
        default_index = sd.default.device[0]
        if isinstance(default_index, int) and 0 <= default_index < len(devices):
            info = devices[default_index]
            if info.get("max_input_channels", 0) > 0 and _is_real_microphone(
                str(info.get("name", ""))
            ):
                return "default"  # le défaut système est déjà un vrai micro

        reals = [
            str(info.get("name", "")).strip()
            for info in devices
            if info.get("max_input_channels", 0) > 0
            and _is_real_microphone(str(info.get("name", "")).strip())
        ]
        # priorité aux périphériques explicitement nommés « micro… »
        for name in reals:
            if "micro" in name.lower():
                return name
        if reals:
            return reals[0]
    except Exception:
        pass
    return "default"


def list_microphones() -> list[tuple[str, str]]:
    """Choix de micro pour les réglages : (valeur, libellé), « default » en tête.

    Les vrais micros physiques sont listés avant les périphériques virtuels
    (mixeurs/loopback), ces derniers étant signalés — ils dégradent la STT.
    """
    choices: list[tuple[str, str]] = [("default", "périphérique par défaut")]
    real: list[tuple[str, str]] = []
    virtual: list[tuple[str, str]] = []
    try:
        import sounddevice as sd

        seen: set[str] = set()
        for info in sd.query_devices():
            name = str(info.get("name", "")).strip()
            if info.get("max_input_channels", 0) > 0 and name and name not in seen:
                seen.add(name)
                if is_virtual_device(name):
                    virtual.append((name, f"{name} · virtuel ⚠"))
                else:
                    real.append((name, name))
    except Exception:
        pass
    return choices + real + virtual
