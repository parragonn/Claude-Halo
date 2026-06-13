"""Capture du parcours démo : F2 → parole simulée → réponse markdown → session.

Usage : uv run python scripts/preview_session.py [largeur hauteur]
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from preview_idle import _NoSecrets, svg_to_text

from halo.ai.fake import DemoProvider
from halo.audio.fake import FakeVoiceEngine
from halo.config.settings import Settings
from halo.coordinator import Coordinator, make_emitter
from halo.core.models import Phase
from halo.ui.terminal_probe import TerminalColors
from halo.ui.tui_app import HaloApp


async def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    size = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (120, 40)
    settings = Settings()
    app = HaloApp(
        settings=settings,
        secrets=_NoSecrets(),
        terminal_colors=TerminalColors(None, None, True),
        save=lambda s: None,
    )
    emit = make_emitter(app)
    engine = FakeVoiceEngine(emit, speed=8)
    app.coordinator = Coordinator(
        app=app, settings=settings, engine=engine, provider=DemoProvider(), window=None
    )
    async with app.run_test(size=size) as pilot:
        await pilot.press("f2")
        coordinator = app.coordinator
        for _ in range(400):
            if coordinator.machine.state.phase is Phase.SESSION_IDLE:
                break
            await pilot.pause(0.05)
        await pilot.pause(0.4)
        svg = app.export_screenshot()
    out = Path(__file__).parent / "preview_session.svg"
    out.write_text(svg, encoding="utf-8")
    print(svg_to_text(svg))
    print(f"\n[état final : {coordinator.machine.state} — SVG : {out}]")


if __name__ == "__main__":
    asyncio.run(main())
