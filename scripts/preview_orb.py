"""Capture headless de l'orbe après ~1,5 s d'animation (SVG + dump texte).

Usage : uv run python scripts/preview_orb.py [largeur hauteur]
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from preview_idle import _NoSecrets, svg_to_text

from halo.config.settings import Settings
from halo.ui.terminal_probe import TerminalColors
from halo.ui.tui_app import HaloApp


async def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    size = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (104, 36)
    app = HaloApp(
        settings=Settings(),
        secrets=_NoSecrets(),
        terminal_colors=TerminalColors(None, None, True),
        save=lambda s: None,
        orb_demo=True,
    )
    async with app.run_test(size=size) as pilot:
        await asyncio.sleep(1.5)
        await pilot.pause()
        svg = app.export_screenshot()
    out = Path(__file__).parent / "preview_orb.svg"
    out.write_text(svg, encoding="utf-8")
    print(svg_to_text(svg))
    print(f"\n[SVG : {out}]")


if __name__ == "__main__":
    asyncio.run(main())
