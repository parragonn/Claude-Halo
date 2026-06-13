"""Gestion des modèles Whisper locaux (cache Hugging Face de faster-whisper)."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from pathlib import Path

# Avant tout import de huggingface_hub (ce module est son seul point d'entrée
# dans Halo) : le backend xet est opaque pour la progression — le backend HTTP
# classique écrit ses blobs au fil de l'eau, observables sur disque.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

_REPOS = {
    "tiny": "Systran/faster-whisper-tiny",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
}

APPROX_SIZE_MB = {"tiny": 80, "small": 250, "medium": 800}

# (octets téléchargés, octets total — 0 si inconnu)
ProgressFn = Callable[[int, int], None]


def hot_size(stt_model: str) -> str:
    """Modèle des chemins chauds (wake, partiels) : jamais plus gros que small —
    la latence y prime, l'amorce biaisée fait le gros de la précision."""
    return "small" if stt_model == "medium" else stt_model


def required_sizes(stt_model: str) -> set[str]:
    return {hot_size(stt_model), stt_model}


def is_cached(size: str) -> bool:
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(_REPOS[size], local_files_only=True)
        return True
    except Exception:
        return False


def repo_size_bytes(size: str) -> int:
    """Taille totale du dépôt (0 si l'info est indisponible)."""
    try:
        from huggingface_hub import HfApi

        info = HfApi().model_info(_REPOS[size], files_metadata=True)
        return sum(sibling.size or 0 for sibling in info.siblings or [])
    except Exception:
        return 0


def _repo_cache_dir(size: str) -> Path:
    from huggingface_hub import constants

    return Path(constants.HF_HUB_CACHE) / f"models--{_REPOS[size].replace('/', '--')}"


def _directory_bytes(path: Path) -> int:
    try:
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    except OSError:
        return 0


def download(size: str, progress: ProgressFn | None = None) -> None:
    """Télécharge (bloquant) — à lancer dans un thread, jamais sur la boucle UI.

    La progression est mesurée sur disque (taille du dossier de cache pendant
    l'écriture) : indépendant des internes de huggingface_hub.
    """
    from huggingface_hub import snapshot_download

    if progress is None:
        snapshot_download(_REPOS[size])
        return

    report = progress
    total = repo_size_bytes(size)
    target = _repo_cache_dir(size)
    already = _directory_bytes(target)
    stop = threading.Event()

    def poll() -> None:
        while not stop.wait(0.15):
            done = _directory_bytes(target) - already
            report(max(0, min(done, total)), total)

    poller = threading.Thread(target=poll, name="halo-download-poll", daemon=True)
    poller.start()
    try:
        snapshot_download(_REPOS[size])
    finally:
        stop.set()
        poller.join(timeout=1.0)
    report(total or _directory_bytes(target), total)


def missing_sizes(stt_model: str) -> list[str]:
    return [size for size in sorted(required_sizes(stt_model)) if not is_cached(size)]
