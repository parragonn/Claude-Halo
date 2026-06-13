"""Simulation de l'orbe : nuage de particules sur une coquille sphérique 3D.

Pure (numpy + rng seedé, zéro I/O, zéro Textual) donc testable et déterministe.
Le widget ne fait qu'afficher les frames produites ici.

Modes :
- LISTENING : audio-réactif — l'énergie (RMS lissé attaque/relâche) dilate la
  sphère, agite les particules et avive la lueur. L'effet n°1 du produit.
- THINKING  : rotation lente + pulsation ~1 Hz — calcul sans agitation.
- CALM      : respiration discrète (orbe parquée / présence au repos).
- STATIC    : nuage figé (reduced motion).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum, auto

import numpy as np

TAU = math.tau


class OrbMode(Enum):
    LISTENING = auto()
    THINKING = auto()
    CALM = auto()
    STATIC = auto()


@dataclass(frozen=True, slots=True)
class OrbFrame:
    """Particules projetées en espace « points » du canvas (orthographique)."""

    xs: np.ndarray
    ys: np.ndarray
    glow: np.ndarray


_ATTACK_S = 0.06
_RELEASE_S = 0.35

_SPIN = {OrbMode.LISTENING: 0.18, OrbMode.THINKING: 0.60, OrbMode.CALM: 0.12}


def _fibonacci_sphere(count: int) -> np.ndarray:
    indices = np.arange(count, dtype=np.float64) + 0.5
    phi = np.arccos(1.0 - 2.0 * indices / count)
    theta = math.pi * (1.0 + math.sqrt(5.0)) * indices
    return np.stack(
        [np.sin(phi) * np.cos(theta), np.cos(phi), np.sin(phi) * np.sin(theta)], axis=1
    )


class OrbPhysics:
    def __init__(self, count: int = 260, seed: int = 7) -> None:
        rng = np.random.default_rng(seed)
        directions = _fibonacci_sphere(count)
        directions += rng.normal(0.0, 0.04, directions.shape)
        self._dirs = directions / np.linalg.norm(directions, axis=1, keepdims=True)

        # ~1/4 de poussière intérieure pour donner du volume au nuage.
        self._radius_base = np.ones(count)
        dust = rng.random(count) < 0.25
        self._radius_base[dust] = rng.uniform(0.25, 0.85, int(dust.sum()))

        self._wobble_freq = rng.uniform(0.5, 1.7, count)
        self._wobble_phase = rng.uniform(0.0, TAU, count)

        self.mode = OrbMode.CALM
        self._level = 0.0
        self.energy = 0.0
        self._spin = 0.0
        self._time = 0.0

    def set_level(self, level: float) -> None:
        """Niveau micro brut 0..1 (consommé en LISTENING via l'enveloppe)."""
        self._level = max(0.0, min(1.0, level))

    def set_mode(self, mode: OrbMode) -> None:
        self.mode = mode

    def step(self, dt: float) -> None:
        if self.mode is OrbMode.STATIC:
            return
        dt = max(0.0, min(0.1, dt))
        target = self._level if self.mode is OrbMode.LISTENING else 0.0
        tau = _ATTACK_S if target > self.energy else _RELEASE_S
        self.energy += (target - self.energy) * (1.0 - math.exp(-dt / tau))
        self._spin += _SPIN[self.mode] * (1.0 + (1.2 * self.energy)) * dt
        self._time += dt

    def _modulation(self) -> tuple[float, float]:
        """(respiration du rayon, amplitude d'agitation) selon le mode."""
        t = self._time
        if self.mode is OrbMode.LISTENING:
            return 0.015 * math.sin(TAU * 0.35 * t), 0.03 + 0.15 * self.energy
        if self.mode is OrbMode.THINKING:
            return 0.05 * math.sin(TAU * 1.0 * t), 0.02
        if self.mode is OrbMode.CALM:
            return 0.03 * math.sin(TAU * 0.22 * t), 0.025
        return 0.0, 0.0

    def frame(self, dot_width: int, dot_height: int) -> OrbFrame:
        center_x, center_y = dot_width / 2.0, dot_height / 2.0
        half = min(dot_width, dot_height) / 2.0
        radius = 0.80 * half

        breathing, wobble_amp = self._modulation()
        dilation = 0.25 * self.energy if self.mode is OrbMode.LISTENING else 0.0
        radius *= 1.0 + dilation + breathing

        cos_a, sin_a = math.cos(self._spin), math.sin(self._spin)
        x = self._dirs[:, 0] * cos_a + self._dirs[:, 2] * sin_a
        z = -self._dirs[:, 0] * sin_a + self._dirs[:, 2] * cos_a
        y = self._dirs[:, 1]

        wobble = 1.0 + wobble_amp * np.sin(
            self._time * self._wobble_freq * TAU + self._wobble_phase
        )
        # Plafonné juste sous le bord : l'orbe embrasse le cadre sans jamais s'y découper.
        r = np.minimum(self._radius_base * wobble * radius, 0.99 * half)

        xs = center_x + x * r
        ys = center_y + y * r

        front = (z + 1.0) * 0.5  # face avant plus lumineuse → profondeur
        rim = self._radius_base  # pourtour clair, cœur profond (spec §6.4)
        glow = 0.18 + 0.50 * rim + 0.32 * front
        if self.mode is OrbMode.LISTENING:
            glow = glow * (0.55 + 0.45 * self.energy)
        elif self.mode is OrbMode.CALM:
            glow = glow * 0.80
        return OrbFrame(xs=xs, ys=ys, glow=np.clip(glow, 0.0, 1.0))
