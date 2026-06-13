"""Capture de l'écran d'accueil (onboarding) avec un rapport d'accélération donné.

Usage : uv run python scripts/preview_onboarding.py [nvidia-ready|nvidia-bare|apple|cpu]
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from preview_idle import _NoSecrets, svg_to_text

from halo.config.settings import Settings
from halo.platform.accel import probe_accelerator
from halo.ui.screens.onboarding import OnboardingScreen
from halo.ui.terminal_probe import TerminalColors
from halo.ui.tui_app import HaloApp

_WIN = {"os_name": "win32", "machine": "amd64"}
_FIXTURES: dict[str, dict[str, object]] = {
    "nvidia-ready": {**_WIN, "cuda_device_count": 1, "cudnn_installed": True},
    "nvidia-bare": {**_WIN, "cuda_device_count": 1, "cudnn_installed": False},
    "apple": {"os_name": "darwin", "machine": "arm64"},
    "cpu": {**_WIN, "cuda_device_count": 0, "cudnn_installed": False},
}


async def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    which = sys.argv[1] if len(sys.argv) > 1 else "nvidia-bare"
    accel = probe_accelerator(**_FIXTURES[which])
    app = HaloApp(
        settings=Settings(),
        secrets=_NoSecrets(),
        terminal_colors=TerminalColors(None, None, True),
        save=lambda s: None,
        accel=accel,
    )
    async with app.run_test(size=(104, 40)) as pilot:
        app.push_screen(OnboardingScreen())
        await pilot.pause()
        await pilot.pause()
        svg = app.export_screenshot()
    out = Path(__file__).parent / "preview_onboarding.svg"
    out.write_text(svg, encoding="utf-8")
    print(svg_to_text(svg))
    print(f"\n[scénario {which} · SVG : {out}]")


if __name__ == "__main__":
    asyncio.run(main())
