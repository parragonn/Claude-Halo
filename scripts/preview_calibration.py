"""Capture de l'assistant de calibration à l'étape résultat (rendu esthétique).

Usage : uv run python scripts/preview_calibration.py [excellent|bon|moyen|faible]
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from preview_idle import _NoSecrets, svg_to_text

from halo.audio.calibration import calibrate
from halo.config.settings import Settings
from halo.ui.terminal_probe import TerminalColors
from halo.ui.tui_app import HaloApp

_SCENARIOS = {
    "excellent": (0.001, 0.05),
    "bon": (0.005, 0.04),
    "moyen": (0.012, 0.04),
    "faible": (0.04, 0.05),
}


class _FakeCalibrator:
    def __init__(self, noise: float, voice: float) -> None:
        self._result = calibrate(noise, voice)

    def run(self, *, on_phase, on_level, on_done, on_error) -> None:  # type: ignore[no-untyped-def]
        on_done(self._result, "comment apprendre Rust et TypeScript")


async def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    which = sys.argv[1] if len(sys.argv) > 1 else "excellent"
    noise, voice = _SCENARIOS[which]
    app = HaloApp(
        settings=Settings(),
        secrets=_NoSecrets(),
        terminal_colors=TerminalColors(None, None, True),
        save=lambda s: None,
    )
    app.calibrator_factory = lambda: _FakeCalibrator(noise, voice)  # type: ignore[assignment]
    async with app.run_test(size=(104, 40)) as pilot:
        app.run_calibration()
        await pilot.pause()
        await pilot.press("enter")  # lance → le faux calibrateur appelle on_done direct
        await pilot.pause()
        await pilot.pause()
        svg = app.export_screenshot()
    out = Path(__file__).parent / "preview_calibration.svg"
    out.write_text(svg, encoding="utf-8")
    print(svg_to_text(svg))
    print(f"\n[scénario {which} · SVG : {out}]")


if __name__ == "__main__":
    asyncio.run(main())
