"""Sonde d'accélération matérielle pour la reconnaissance vocale.

Au premier lancement, l'app détecte ce que CTranslate2 peut réellement
exploiter : GPU NVIDIA (CUDA) → accéléré ; Apple Silicon → CPU Accelerate
(déjà rapide) ; AMD/Intel/aucun → CPU. Si la détection se trompe, le réglage
« Accélération STT » (Réglages ▸ Voix) reste la source de vérité.

Les entrées sont injectables pour les tests ; la sonde réelle n'échoue jamais.
"""

from __future__ import annotations

import platform as platform_module
import sys
import sysconfig
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AccelReport:
    kind: str  # nvidia | apple | cpu
    cuda_ready: bool
    label: str  # affiché à l'onboarding / diagnostic
    hint: str = ""  # action suggérée quand quelque chose manque


def _real_cuda_device_count() -> int:
    try:
        import ctranslate2

        return int(ctranslate2.get_cuda_device_count())
    except Exception:
        return 0


def _real_cudnn_installed() -> bool:
    try:
        return (Path(sysconfig.get_paths()["purelib"]) / "nvidia" / "cudnn").is_dir()
    except Exception:
        return False


def probe_accelerator(
    *,
    os_name: str | None = None,
    machine: str | None = None,
    cuda_device_count: int | None = None,
    cudnn_installed: bool | None = None,
) -> AccelReport:
    os_name = os_name if os_name is not None else sys.platform
    machine = machine if machine is not None else platform_module.machine().lower()

    if os_name == "darwin" and machine in ("arm64", "aarch64"):
        return AccelReport(
            kind="apple",
            cuda_ready=False,
            label="Apple Silicon · CPU Accelerate (rapide)",
        )

    count = cuda_device_count if cuda_device_count is not None else _real_cuda_device_count()
    if count > 0:
        cudnn = cudnn_installed if cudnn_installed is not None else _real_cudnn_installed()
        if cudnn:
            return AccelReport(
                kind="nvidia", cuda_ready=True, label="GPU NVIDIA · CUDA prêt"
            )
        return AccelReport(
            kind="nvidia",
            cuda_ready=False,
            label="GPU NVIDIA · CUDA non installé",
            hint="relance avec « uv run --extra cuda halo »",
        )
    return AccelReport(kind="cpu", cuda_ready=False, label="CPU (aucun GPU compatible)")
