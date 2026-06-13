"""Détection des couleurs du terminal (spec §6.2) — best-effort, jamais bloquant.

Chaîne de repli : OSC 10/11 (couleurs réelles fg/bg) → COLORFGBG → sombre par
défaut. Les helpers de parsing sont purs et testés ; la requête elle-même est
isolée et tolérante aux pannes (timeout court, restauration du mode console).
"""

from __future__ import annotations

import os
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass

type RGB = tuple[int, int, int]

_OSC_RGB = re.compile(r"rgba?:([0-9a-fA-F]{1,4})/([0-9a-fA-F]{1,4})/([0-9a-fA-F]{1,4})")
_OSC_HEX = re.compile(r"#([0-9a-fA-F]{6})")
_OSC_REPLY = re.compile("\x1b\\]1([01]);([^\x07\x1b]*)")


@dataclass(frozen=True, slots=True)
class TerminalColors:
    """Couleurs détectées ; `dark` est toujours résolu (sombre par défaut)."""

    foreground: RGB | None
    background: RGB | None
    dark: bool


def parse_osc_color(reply: str) -> RGB | None:
    """Extrait un RGB d'une réponse OSC 10/11 (`rgb:RRRR/GGGG/BBBB`, `#RRGGBB`…)."""
    match = _OSC_RGB.search(reply)
    if match is not None:

        def scale(component: str) -> int:
            return round(int(component, 16) * 255 / ((1 << (4 * len(component))) - 1))

        r, g, b = (scale(c) for c in match.groups())
        return (r, g, b)
    hex_match = _OSC_HEX.search(reply)
    if hex_match is not None:
        value = hex_match.group(1)
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    return None


def relative_luminance(rgb: RGB) -> float:
    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def is_dark(rgb: RGB) -> bool:
    return relative_luminance(rgb) < 0.5


def darkness_from_colorfgbg(value: str) -> bool | None:
    """`COLORFGBG` vaut p. ex. `15;0` (fg;bg) : fond ANSI 0-6 ou 8 = sombre."""
    parts = value.split(";")
    if len(parts) < 2:
        return None
    try:
        bg = int(parts[-1])
    except ValueError:
        return None
    return bg in {0, 1, 2, 3, 4, 5, 6, 8}


def detect_terminal_colors(override: str = "auto") -> TerminalColors:
    """Détermine fond clair/sombre (+ RGB réels si le terminal répond à OSC)."""
    env_override = os.environ.get("HALO_THEME", "").lower()
    forced = override if override in ("dark", "light") else env_override
    if forced in ("dark", "light"):
        return TerminalColors(None, None, forced == "dark")

    fg = bg = None
    if sys.stdin.isatty() and sys.stdout.isatty():
        try:
            replies = _query_osc_colors()
            fg = parse_osc_color(replies.get(10, ""))
            bg = parse_osc_color(replies.get(11, ""))
        except Exception:  # la détection ne doit jamais empêcher le lancement
            fg = bg = None
    if bg is not None:
        return TerminalColors(fg, bg, is_dark(bg))
    hint = darkness_from_colorfgbg(os.environ.get("COLORFGBG", ""))
    return TerminalColors(fg, bg, True if hint is None else hint)


def _parse_replies(buffer: str) -> dict[int, str]:
    replies: dict[int, str] = {}
    for code, payload in _OSC_REPLY.findall(buffer):
        replies[10 if code == "0" else 11] = payload
    return replies


def _collect(read_available: Callable[[], str], timeout: float) -> dict[int, str]:
    buffer = ""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        chunk = read_available()
        if chunk:
            buffer += chunk
            if buffer.count("\x07") + buffer.count("\x1b\\") >= 2:
                break
        else:
            time.sleep(0.01)
    return _parse_replies(buffer)


def _query_osc_colors(timeout: float = 0.25) -> dict[int, str]:
    return _query_backend("\x1b]10;?\x07\x1b]11;?\x07", timeout)


if sys.platform == "win32":

    def _query_backend(query: str, timeout: float) -> dict[int, str]:
        import ctypes
        import msvcrt

        kernel32 = ctypes.windll.kernel32
        handle_in = kernel32.GetStdHandle(-10)
        saved = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle_in, ctypes.byref(saved)):
            return {}
        enable_vt_input = 0x0200
        processed, line, echo = 0x0001, 0x0002, 0x0004
        kernel32.SetConsoleMode(
            handle_in, (saved.value | enable_vt_input) & ~(processed | line | echo)
        )
        try:
            sys.stdout.write(query)
            sys.stdout.flush()

            def read_available() -> str:
                chars: list[str] = []
                while msvcrt.kbhit():
                    chars.append(msvcrt.getwch())
                return "".join(chars)

            return _collect(read_available, timeout)
        finally:
            kernel32.SetConsoleMode(handle_in, saved.value)

else:

    def _query_backend(query: str, timeout: float) -> dict[int, str]:
        import select
        import termios
        import tty

        fd = sys.stdin.fileno()
        saved = termios.tcgetattr(fd)
        tty.setcbreak(fd)
        try:
            sys.stdout.write(query)
            sys.stdout.flush()

            def read_available() -> str:
                ready, _, _ = select.select([fd], [], [], 0)
                return os.read(fd, 1024).decode("utf-8", "replace") if ready else ""

            return _collect(read_available, timeout)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)
