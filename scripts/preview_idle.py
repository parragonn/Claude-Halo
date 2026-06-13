"""Capture headless de l'écran d'accueil : SVG + dump texte ligne à ligne.

Usage : uv run python scripts/preview_idle.py [largeur hauteur]
Produit scripts/preview.svg et affiche une reconstruction texte de l'écran.
"""

from __future__ import annotations

import asyncio
import html
import re
import sys
from collections import defaultdict
from pathlib import Path

from halo.config.settings import Settings
from halo.ui.terminal_probe import TerminalColors
from halo.ui.tui_app import HaloApp


class _NoSecrets:
    def get_api_key(self) -> str | None:
        return None

    def set_api_key(self, value: str) -> bool:
        return True

    def clear_api_key(self) -> bool:
        return True


def svg_to_text(svg: str) -> str:
    """Reconstitue les lignes de l'écran depuis les runs <text> du SVG."""
    runs: dict[float, list[tuple[float, str]]] = defaultdict(list)
    for tag, content in re.findall(r"<text([^>]*)>(.*?)</text>", svg, flags=re.S):
        x_match = re.search(r'x="([\d.]+)"', tag)
        y_match = re.search(r'y="([\d.]+)"', tag)
        if x_match is None or y_match is None:
            continue
        runs[float(y_match.group(1))].append((float(x_match.group(1)), html.unescape(content)))
    lines = []
    for y in sorted(runs):
        line = "".join(text for _, text in sorted(runs[y], key=lambda item: item[0]))
        lines.append(line.rstrip())
    return "\n".join(lines)


async def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    size = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (104, 42)
    app = HaloApp(
        settings=Settings(),
        secrets=_NoSecrets(),
        terminal_colors=TerminalColors(None, None, True),
        save=lambda s: None,
    )
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        svg = app.export_screenshot()
    out = Path(__file__).parent / "preview.svg"
    out.write_text(svg, encoding="utf-8")
    print(svg_to_text(svg))
    print(f"\n[SVG : {out}]")


if __name__ == "__main__":
    asyncio.run(main())
