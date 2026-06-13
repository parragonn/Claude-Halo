"""Transcription locale (faster-whisper) + thread de jobs STT.

Trois sortes de jobs, par priorité : finale (obligatoire) > wake (fenêtre
glissante) > partiel (remplaçable par plus récent). Whisper tourne ici, jamais
sur le thread audio ni la boucle UI.
"""

from __future__ import annotations

import os
import sys
import sysconfig
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

_CPU_THREADS = min(8, max(4, os.cpu_count() or 4))

_cuda_dlls_added = False


def _enable_cuda_dlls() -> None:
    """Windows : les roues pip `nvidia-*-cu12` rangent leurs DLL hors du PATH.
    On les déclare au chargeur de DEUX façons (ceinture + bretelles) avant
    d'initialiser CUDA : `add_dll_directory` (moderne) ET le PATH du process —
    ce dernier est nécessaire pour que cuBLAS résolve ses dépendances
    transitives (cudart…), qu'`add_dll_directory` seul ne couvre pas toujours."""
    global _cuda_dlls_added
    if _cuda_dlls_added or sys.platform != "win32":
        return
    _cuda_dlls_added = True
    nvidia_root = Path(sysconfig.get_paths()["purelib"]) / "nvidia"
    if not nvidia_root.is_dir():
        return
    bin_dirs: list[str] = []
    for package in sorted(nvidia_root.iterdir()):
        bin_dir = package / "bin"
        if bin_dir.is_dir():
            os.add_dll_directory(str(bin_dir))
            bin_dirs.append(str(bin_dir))
    if bin_dirs:
        os.environ["PATH"] = os.pathsep.join([*bin_dirs, os.environ.get("PATH", "")])


def cuda_libs_present() -> bool:
    """Les bibliothèques CUDA (roues pip nvidia-*) sont-elles installées ?
    Sans elles, CTranslate2 échoue à la PREMIÈRE inférence (chargement paresseux
    de cuBLAS), pas à la construction du modèle — d'où ce contrôle en amont."""
    try:
        nvidia = Path(sysconfig.get_paths()["purelib"]) / "nvidia"
        return (nvidia / "cublas").is_dir() and (nvidia / "cudnn").is_dir()
    except Exception:
        return False


def resolve_device(wanted: str, cuda_failed: bool, libs_present: bool) -> tuple[str, str]:
    """(device, compute_type) effectifs pour CTranslate2 — pur, testable.

    CPU si : explicitement demandé, CUDA déjà constaté défaillant, ou
    bibliothèques CUDA absentes (qu'on ait demandé « cuda » ou « auto »)."""
    if wanted == "cpu" or cuda_failed or not libs_present:
        return ("cpu", "int8")
    return ("cuda", "float16")


def _probe_inference(model: Any) -> None:
    """Mini-inférence (0,5 s de silence) pour déclencher le chargement complet
    des bibliothèques GPU et révéler tout de suite une DLL manquante."""
    segments, _info = model.transcribe(
        np.zeros(8000, dtype=np.float32), language="fr", beam_size=1, without_timestamps=True
    )
    list(segments)  # consomme le générateur paresseux → force l'exécution


class ModelStore:
    """Charge et met en cache les modèles CTranslate2.

    GPU (CUDA float16) quand demandé/possible — ~20× plus rapide qu'un CPU —
    avec repli silencieux sur CPU int8 si CUDA est indisponible.
    """

    def __init__(self, device_provider: Callable[[], str] | None = None) -> None:
        self._device_provider = device_provider or (lambda: "auto")
        self._models: dict[tuple[str, str], Any] = {}
        self._lock = threading.Lock()
        self._cuda_failed = False
        self.cuda_error = ""

    @property
    def active_device(self) -> str:
        return resolve_device(
            self._device_provider(), self._cuda_failed, cuda_libs_present()
        )[0]

    def get(self, size: str) -> Any:
        with self._lock:
            device, _compute_type = resolve_device(
                self._device_provider(), self._cuda_failed, cuda_libs_present()
            )
            cached = self._models.get((size, device))
            if cached is not None:
                return cached
            from faster_whisper import WhisperModel

            if device == "cuda":
                try:
                    _enable_cuda_dlls()
                    model = WhisperModel(size, device="cuda", compute_type="float16")
                    # cuBLAS/cuDNN se chargent à la 1re inférence : on la force ici
                    # pour détecter une DLL manquante MAINTENANT (pas en plein usage).
                    _probe_inference(model)
                    self._models[(size, "cuda")] = model
                    return model
                except Exception as exc:
                    self._cuda_failed = True
                    self.cuda_error = str(exc)[:160]
            model = WhisperModel(
                size, device="cpu", compute_type="int8", cpu_threads=_CPU_THREADS
            )
            self._models[(size, "cpu")] = model
            return model


_INITIAL_PROMPTS = {
    # Le style de l'amorce est imité par Whisper : un exemple de français
    # mêlé d'anglais technique l'autorise à écrire « Rust » plutôt que « reste ».
    "fr": (
        "Question dictée à l'oral, en français, avec des termes techniques "
        "anglais comme Rust, Python ou framework."
    ),
    "en": "A question dictated out loud, in plain English.",
}

_BASE_LEXICON = (
    "Rust, Python, TypeScript, JavaScript, C++, Go, Docker, Linux, Windows, "
    "GitHub, API, JSON, SQL, backend, frontend, framework, machine learning, "
    "open source, terminal, cloud, Claude, Anthropic, Whisper"
)


def merged_lexicon(user_lexicon: str = "") -> str:
    """Lexique de base + termes de l'utilisateur, borné (l'amorce Whisper
    est limitée à ~224 tokens)."""
    merged = _BASE_LEXICON
    extra = " ".join(user_lexicon.split())
    if extra:
        merged = f"{extra}, {merged}"
    return merged[:400]


def _build_prompt(
    language: str | None, bias: str | None, lexicon: str, quality: bool
) -> str | None:
    clause = f"Termes possibles : {lexicon}." if lexicon else ""
    if bias:
        return f"{bias}. {clause}".strip()
    style = _INITIAL_PROMPTS.get(language or "")
    if quality and style:
        return f"{style} {clause}".strip()
    if clause:
        return clause
    return None


def normalize_audio(samples: np.ndarray, *, target_peak: float = 0.9) -> np.ndarray:
    """Remonte un signal trop faible vers un pic exploitable (micro discret =
    précision Whisper en chute libre). Ne touche pas un signal déjà sain."""
    if samples.size == 0:
        return samples
    peak = float(np.abs(samples).max())
    if peak < 1e-4 or peak >= 0.30:
        return samples
    return (samples * (target_peak / peak)).astype(np.float32)


class Transcriber:
    def __init__(self, store: ModelStore) -> None:
        self._store = store

    def warm_up(self, size: str) -> None:
        """Charge le modèle s'il ne l'est pas déjà (premier chargement long)."""
        self._store.get(size)

    def transcribe(
        self,
        samples: np.ndarray,
        *,
        size: str,
        language: str | None,
        quality: bool = False,
        bias: str | None = None,
        lexicon: str = "",
        gain: float = 1.0,
    ) -> str:
        """`quality=True` pour la finale : filtre VAD + amorce de contexte.
        `bias` souffle un texte attendu (la phrase d'activation) ; `lexicon`
        autorise le franglais technique ; `gain` est le gain de normalisation
        calibré (1.0 = non calibré → boost auto par pic). Décodage vorace
        partout : au banc, amorce+lexique en vorace égalait le beam search."""
        if samples.size < 1600:  # < 0,1 s : rien d'exploitable
            return ""
        if gain != 1.0:  # gain calibré : on lui fait confiance + clip de sécurité
            audio = np.clip(samples * gain, -1.0, 1.0).astype(np.float32)
        else:
            audio = normalize_audio(samples)
        prompt = _build_prompt(language, bias, lexicon, quality)
        model = self._store.get(size)
        segments, _info = model.transcribe(
            audio,
            language=language,
            beam_size=1,
            vad_filter=quality,
            initial_prompt=prompt,
            without_timestamps=True,
            condition_on_previous_text=False,
        )
        return "".join(segment.text for segment in segments).strip()


class SttJobs(threading.Thread):
    """File de jobs à emplacements : wake/partiel/brouillon gardent le plus récent.

    Le « brouillon » est une finale spéculative lancée dès ~1 s de silence :
    si plus rien n'est dit avant la barrière de fin de question, son résultat
    est déjà prêt — zéro attente perçue.
    """

    def __init__(
        self,
        transcriber: Transcriber,
        *,
        final_size: Callable[[], str],
        hot_size: Callable[[], str],
        language: Callable[[], str | None],
        wake_bias: Callable[[], str],
        lexicon: Callable[[], str],
        gain: Callable[[], float],
        on_wake_text: Callable[[str], None],
        on_partial: Callable[[str], None],
        on_final: Callable[[str], None],
        on_draft: Callable[[int, str], None],
        on_error: Callable[[str], None],
        preload: tuple[str, ...] = (),
    ) -> None:
        super().__init__(name="halo-stt", daemon=True)
        self._transcriber = transcriber
        self._final_size = final_size
        self._hot_size = hot_size
        self._language = language
        self._wake_bias = wake_bias
        self._lexicon = lexicon
        self._gain = gain
        self._on_wake_text = on_wake_text
        self._on_partial = on_partial
        self._on_final = on_final
        self._on_draft = on_draft
        self._on_error = on_error
        self._preload = preload
        self._cond = threading.Condition()
        self._wake: np.ndarray | None = None
        self._partial: np.ndarray | None = None
        self._draft: tuple[int, np.ndarray] | None = None
        self._finals: list[np.ndarray] = []
        self._running = True

    def submit_wake(self, samples: np.ndarray) -> None:
        with self._cond:
            self._wake = samples
            self._cond.notify()

    def submit_partial(self, samples: np.ndarray) -> None:
        with self._cond:
            self._partial = samples
            self._cond.notify()

    def submit_draft(self, token: int, samples: np.ndarray) -> None:
        with self._cond:
            self._draft = (token, samples)
            self._cond.notify()

    def submit_final(self, samples: np.ndarray) -> None:
        with self._cond:
            self._finals.append(samples)
            self._partial = None  # la finale rend partiels et brouillons caducs
            self._draft = None
            self._cond.notify()

    def shutdown(self) -> None:
        with self._cond:
            self._running = False
            self._cond.notify()

    def run(self) -> None:
        try:
            for size in self._preload:
                self._transcriber._store.get(size)
        except Exception as exc:
            self._on_error(str(exc)[:120])
            return
        while True:
            with self._cond:
                while self._running and not (
                    self._finals
                    or self._draft is not None
                    or self._wake is not None
                    or self._partial is not None
                ):
                    self._cond.wait(timeout=0.5)
                if not self._running:
                    return
                draft_token = -1
                if self._finals:
                    kind, samples = "final", self._finals.pop(0)
                elif self._draft is not None:
                    kind = "draft"
                    draft_token, samples = self._draft
                    self._draft = None
                elif self._wake is not None:
                    kind, samples = "wake", self._wake
                    self._wake = None
                else:
                    assert self._partial is not None
                    kind, samples = "partial", self._partial
                    self._partial = None
            try:
                gain = self._gain()
                if kind in ("final", "draft"):
                    # Recette validée au banc : amorce de la phrase d'activation
                    # + lexique + filtre VAD — la plus fidèle sur voix réelle.
                    text = self._transcriber.transcribe(
                        samples,
                        size=self._final_size(),
                        language=self._language(),
                        quality=True,
                        bias=self._wake_bias(),
                        lexicon=self._lexicon(),
                        gain=gain,
                    )
                    if kind == "final":
                        self._on_final(text)
                    else:
                        self._on_draft(draft_token, text)
                elif kind == "wake":
                    # Modèle « chaud » + amorce de la phrase attendue : réactif.
                    text = self._transcriber.transcribe(
                        samples,
                        size=self._hot_size(),
                        language=self._language(),
                        bias=self._wake_bias(),
                        lexicon=self._lexicon(),
                        gain=gain,
                    )
                    self._on_wake_text(text)
                else:
                    text = self._transcriber.transcribe(
                        samples,
                        size=self._hot_size(),
                        language=self._language(),
                        lexicon=self._lexicon(),
                        gain=gain,
                    )
                    if text:
                        self._on_partial(text)
            except Exception as exc:
                if kind == "final":
                    self._on_final("")
                    self._on_error(str(exc)[:120])
