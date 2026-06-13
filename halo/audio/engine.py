"""Le moteur vocal réel : micro → VAD → wake STT → capture → transcription.

Threading :
- callback PortAudio → file de blocs (jamais bloquée) ;
- thread « worker » : RMS, VAD, fenêtres, état WAKE/CAPTURE (seul écrivain) ;
- thread « stt » : Whisper (jobs à priorité, voir halo.audio.stt) ;
- commandes inter-threads via une petite file traitée par le worker.

Tous les événements sortent par `emit`, rendu thread-safe par la composition.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from enum import Enum, auto
from typing import cast

import numpy as np

from halo.audio.capture import (
    BLOCK_SECONDS,
    SAMPLE_RATE,
    BlockRing,
    EnergyVad,
    MicError,
    MicSource,
    block_rms,
    rms_to_level,
)
from halo.audio.stt import ModelStore, SttJobs, Transcriber, merged_lexicon
from halo.audio.wake_word import WakePhraseMatcher, strip_phrase_prefix
from halo.audio.whisper_models import hot_size, required_sizes
from halo.config.settings import Settings
from halo.core import events as ev
from halo.core.models import AudioFaultKind


class _Mode(Enum):
    WAKE = auto()
    CAPTURE = auto()


_WAKE_WINDOW_S = 4.5
_WAKE_DECODE_S = 3.0  # fenêtre passée à Whisper : la phrase y tient, décodage plus court
_WAKE_STT_EVERY_S = 1.1
_WAKE_END_SILENCE_S = 0.7
_PARTIAL_EVERY_S = 1.4
_DRAFT_SILENCE_S = 1.0  # brouillon spéculatif de la finale dès ce silence
_TAIL_S = 1.2
_NO_SPEECH_ABORT_S = 10.0
_MAX_UTTERANCE_S = 90.0


class SttVoiceEngine:
    def __init__(
        self,
        settings: Settings,
        emit: Callable[[ev.Event], None],
        *,
        cuda_possible: bool = True,
    ) -> None:
        self._settings = settings
        self._emit = emit
        self._blocks: queue.Queue[np.ndarray] = queue.Queue(maxsize=64)
        self._commands: queue.Queue[tuple[str, object]] = queue.Queue()

        def device_choice() -> str:
            wanted = settings.voice.stt_device
            if wanted == "auto" and not cuda_possible:
                return "cpu"  # la sonde a tranché : inutile de tenter CUDA
            return wanted

        self.store = ModelStore(device_choice)  # partagé avec la calibration
        self._stt: SttJobs | None = None
        self._mic: MicSource | None = None
        self._worker: threading.Thread | None = None
        self._running = False
        self._followup = False
        self._generation = 0  # invalide les anciens workers lors d'un redémarrage

    # ── API (thread UI) ──────────────────────────────────────────────────────

    def start(self) -> bool:
        if self._running:
            return True
        self._running = True
        self._generation += 1
        generation = self._generation
        self._stt = SttJobs(
            Transcriber(self.store),
            final_size=lambda: self._settings.voice.stt_model,
            hot_size=lambda: hot_size(self._settings.voice.stt_model),
            language=self._language,
            wake_bias=lambda: self._settings.voice.wake_phrase,
            lexicon=lambda: merged_lexicon(self._settings.voice.lexicon),
            gain=lambda: self._settings.voice.calibrated_gain,
            on_wake_text=self._on_wake_text,
            on_partial=lambda text: self._emit(ev.TranscriptPartial(text=text)),
            on_final=self._emit_final,
            on_draft=lambda token, text: self._commands.put(("draft_ready", (token, text))),
            on_error=lambda detail: self._emit(
                ev.AudioFault(kind=AudioFaultKind.ENGINE_ERROR, detail=detail)
            ),
            preload=tuple(sorted(required_sizes(self._settings.voice.stt_model))),
        )
        self._mic = MicSource(
            self._settings.voice.mic_device, self._blocks, on_lost=self._on_mic_lost
        )
        try:
            self._mic.start()
        except MicError as error:
            self._running = False
            self._emit(ev.AudioFault(kind=error.kind, detail=error.detail))
            return False
        self._stt.start()
        self._worker = threading.Thread(
            target=self._run, args=(generation,), name="halo-audio", daemon=True
        )
        self._worker.start()
        return True

    def stop(self) -> None:
        self._running = False
        self._generation += 1
        if self._mic is not None:
            self._mic.stop()
        if self._stt is not None:
            self._stt.shutdown()

    def start_capture(self) -> None:
        self._commands.put(("capture", None))

    def stop_capture(self) -> None:
        self._commands.put(("wake", None))

    def set_followup_mode(self, enabled: bool) -> None:
        self._followup = enabled

    # ── callbacks autres threads ─────────────────────────────────────────────

    def _language(self) -> str | None:
        language = self._settings.ai.language
        return language if language in ("fr", "en") else None

    def _emit_final(self, text: str) -> None:
        self._emit(
            ev.TranscriptFinal(
                text=strip_phrase_prefix(text, self._settings.voice.wake_phrase)
            )
        )

    def _on_mic_lost(self) -> None:
        if self._running:
            self._emit(ev.AudioFault(kind=AudioFaultKind.DEVICE_LOST))

    def _on_wake_text(self, text: str) -> None:
        matcher = WakePhraseMatcher(self._settings.voice.wake_phrase)
        result = matcher.match(text, require_all=not self._followup)
        if result is not None:
            self._commands.put(("wake_hit", result.residual_text))

    # ── thread worker (seul écrivain de l'état audio) ────────────────────────

    def _run(self, generation: int) -> None:
        vad = EnergyVad(
            self._settings.voice.sensitivity,
            noise_floor=self._settings.voice.noise_floor,
        )
        mode = _Mode.WAKE
        ring = BlockRing(_WAKE_WINDOW_S)
        utterance: list[np.ndarray] = []
        utterance_s = 0.0
        had_speech = False
        speech_since_stt = 0.0
        since_partial = 0.0
        pending_tail: np.ndarray | None = None
        wake_armed = True  # réarmé après un silence, contre les doubles détections
        draft_seq = 0  # n° du brouillon spéculatif en cours de validité
        draft_requested = False
        pending_draft: str | None = None  # finale déjà transcrite, prête à servir

        while self._running and generation == self._generation:
            try:
                block = self._blocks.get(timeout=0.25)
            except queue.Empty:
                block = None

            while True:
                try:
                    command, payload = self._commands.get_nowait()
                except queue.Empty:
                    break
                if command == "capture":
                    mode = _Mode.CAPTURE
                    utterance = (
                        [pending_tail]
                        if pending_tail is not None and pending_tail.size
                        else []
                    )
                    utterance_s = sum(b.size for b in utterance) / SAMPLE_RATE
                    pending_tail = None
                    had_speech = vad.speaking
                    since_partial = 0.0
                    draft_seq += 1
                    draft_requested = False
                    pending_draft = None
                    vad.start_utterance()
                elif command == "wake" and mode is _Mode.CAPTURE:
                    mode = _Mode.WAKE
                    utterance = []
                    ring.clear()
                    draft_seq += 1
                    pending_draft = None
                elif command == "draft_ready":
                    seq, text = cast("tuple[int, str]", payload)
                    if mode is _Mode.CAPTURE and seq == draft_seq:
                        pending_draft = text
                elif command == "wake_hit" and mode is _Mode.WAKE and wake_armed:
                    wake_armed = False
                    pending_tail = ring.tail(_TAIL_S)
                    self._emit(ev.WakeDetected(residual_text=str(payload)))

            if block is None:
                continue

            rms = block_rms(block)
            vad.update(rms)
            self._emit(ev.AmplitudeChanged(level=rms_to_level(rms)))

            if mode is _Mode.WAKE:
                ring.append(block)
                if vad.speaking:
                    speech_since_stt += BLOCK_SECONDS
                    if speech_since_stt >= _WAKE_STT_EVERY_S and self._stt is not None:
                        speech_since_stt = 0.0
                        self._stt.submit_wake(ring.tail(_WAKE_DECODE_S))
                elif vad.silence_for > _WAKE_END_SILENCE_S:
                    if speech_since_stt > 0.35 and self._stt is not None:
                        self._stt.submit_wake(ring.tail(_WAKE_DECODE_S))
                    speech_since_stt = 0.0
                    wake_armed = True
            else:
                utterance.append(block)
                utterance_s += BLOCK_SECONDS
                if vad.speaking:
                    if not had_speech:
                        had_speech = True
                        self._emit(ev.SpeechStarted())
                    if draft_requested or pending_draft is not None:
                        draft_seq += 1  # la parole reprend : le brouillon est caduc
                        draft_requested = False
                        pending_draft = None
                    since_partial += BLOCK_SECONDS
                    if since_partial >= _PARTIAL_EVERY_S and self._stt is not None:
                        since_partial = 0.0
                        self._stt.submit_partial(np.concatenate(utterance))
                elif (
                    had_speech
                    and not draft_requested
                    and vad.silence_for >= _DRAFT_SILENCE_S
                    and self._stt is not None
                ):
                    # Probable fin de question : on transcrit en avance — quand la
                    # barrière de silence tombera, le texte sera déjà prêt.
                    draft_requested = True
                    draft_seq += 1
                    self._stt.submit_draft(draft_seq, np.concatenate(utterance))
                timeout = self._settings.voice.silence_timeout_s
                ended = had_speech and vad.silence_for >= timeout
                aborted = not had_speech and utterance_s >= _NO_SPEECH_ABORT_S
                if ended or aborted or utterance_s >= _MAX_UTTERANCE_S:
                    mode = _Mode.WAKE
                    ring.clear()
                    wake_armed = False
                    self._emit(ev.SpeechEnded())
                    if not had_speech:
                        self._emit(ev.TranscriptFinal(text=""))
                    elif pending_draft is not None:
                        self._emit_final(pending_draft)  # déjà calculée : zéro attente
                    elif self._stt is not None:
                        self._stt.submit_final(np.concatenate(utterance))
                    utterance = []
                    draft_seq += 1
                    draft_requested = False
                    pending_draft = None
