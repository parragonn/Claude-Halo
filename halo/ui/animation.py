"""Politique d'animation centralisée — un seul interrupteur pour tout le mouvement.

Reduced-motion (config ou HALO_REDUCED_MOTION=1) : transitions instantanées,
orbe statique, texte sans fondu. Chaque animation de l'app passe par ici.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

EASING = "in_out_cubic"
DUR_FAST = 0.18
DUR_BASE = 0.30
DUR_SLOW = 0.42
ORB_FPS = 30.0


def env_reduced_motion() -> bool:
    return bool(os.environ.get("HALO_REDUCED_MOTION"))


@dataclass(frozen=True, slots=True)
class MotionPolicy:
    enabled: bool

    @classmethod
    def from_settings(cls, reduced_motion: bool) -> MotionPolicy:
        return cls(enabled=not (reduced_motion or env_reduced_motion()))

    def duration(self, seconds: float) -> float:
        """Durée effective d'une transition (0 = instantané)."""
        return seconds if self.enabled else 0.0

    @property
    def orb_fps(self) -> float:
        """Cadence de simulation de l'orbe (0 = nuage statique)."""
        return ORB_FPS if self.enabled else 0.0
