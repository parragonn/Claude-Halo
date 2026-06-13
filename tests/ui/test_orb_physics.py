"""Simulation de l'orbe : déterminisme, enveloppe, dilatation, bornes."""

from __future__ import annotations

import math

import numpy as np

from halo.ui.widgets.orb_physics import OrbMode, OrbPhysics

DOTS = (96, 80)


def stepped(mode: OrbMode, level: float, steps: int, seed: int = 7) -> OrbPhysics:
    physics = OrbPhysics(seed=seed)
    physics.set_mode(mode)
    physics.set_level(level)
    for _ in range(steps):
        physics.step(1 / 30)
    return physics


def mean_radius(physics: OrbPhysics) -> float:
    frame = physics.frame(*DOTS)
    cx, cy = DOTS[0] / 2, DOTS[1] / 2
    return float(np.hypot(frame.xs - cx, frame.ys - cy).mean())


def test_deterministic_given_seed() -> None:
    a = stepped(OrbMode.LISTENING, 0.8, 30, seed=3)
    b = stepped(OrbMode.LISTENING, 0.8, 30, seed=3)
    fa, fb = a.frame(*DOTS), b.frame(*DOTS)
    assert np.allclose(fa.xs, fb.xs) and np.allclose(fa.ys, fb.ys)
    assert np.allclose(fa.glow, fb.glow)


def test_energy_envelope_attack_and_release() -> None:
    physics = OrbPhysics()
    physics.set_mode(OrbMode.LISTENING)
    physics.set_level(1.0)
    physics.step(0.06)
    assert math.isclose(physics.energy, 1 - math.exp(-1), rel_tol=0.05)
    physics.set_level(0.0)
    before = physics.energy
    for _ in range(12):  # 0,4 s en pas de 1/30 (step plafonne dt à 0,1 s)
        physics.step(1 / 30)
    assert physics.energy < before * 0.45


def test_voice_dilates_the_orb() -> None:
    quiet = stepped(OrbMode.LISTENING, 0.0, 60)
    loud = stepped(OrbMode.LISTENING, 1.0, 60)
    assert mean_radius(loud) > mean_radius(quiet) * 1.12


def test_listening_glow_brightens_with_voice() -> None:
    quiet = stepped(OrbMode.LISTENING, 0.0, 60)
    loud = stepped(OrbMode.LISTENING, 1.0, 60)
    assert loud.frame(*DOTS).glow.mean() > quiet.frame(*DOTS).glow.mean() * 1.2


def test_particles_stay_inside_canvas_at_full_blast() -> None:
    physics = OrbPhysics()
    physics.set_mode(OrbMode.LISTENING)
    physics.set_level(1.0)
    for _ in range(120):
        physics.step(1 / 30)
        frame = physics.frame(*DOTS)
        assert frame.xs.min() >= 0 and frame.xs.max() < DOTS[0]
        assert frame.ys.min() >= 0 and frame.ys.max() < DOTS[1]


def test_thinking_pulses_slowly() -> None:
    physics = OrbPhysics()
    physics.set_mode(OrbMode.THINKING)
    radii = []
    for _ in range(45):  # 1,5 s -> couvre une pulsation ~1 Hz
        physics.step(1 / 30)
        radii.append(mean_radius(physics))
    assert max(radii) - min(radii) > 0.5


def test_static_mode_freezes_the_cloud() -> None:
    physics = OrbPhysics()
    physics.set_mode(OrbMode.STATIC)
    first = physics.frame(*DOTS)
    physics.step(1.0)
    second = physics.frame(*DOTS)
    assert np.array_equal(first.xs, second.xs)
    assert np.array_equal(first.ys, second.ys)
