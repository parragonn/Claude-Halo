"""Lancement au démarrage : clé Run (Windows) / LaunchAgent (macOS, best effort).

La commande relance l'app avec l'interpréteur courant (`python -m halo`) dans
un terminal : Windows Terminal si présent, sinon une console classique.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "ClaudeHalo"
_PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / "com.claude-halo.plist"


def startup_command(python: str | None = None, wt: str | None = None) -> str:
    """Construit la ligne de commande de démarrage (pur, testable)."""
    python = python or sys.executable
    if wt is None:
        wt = shutil.which("wt") or ""
    if wt:
        return f'"{wt}" --title "Claude Halo" "{python}" -m halo'
    return f'cmd /c start "Claude Halo" "{python}" -m halo'


def apply_autostart(enabled: bool) -> bool:
    try:
        if sys.platform == "win32":
            return _apply_windows(enabled)
        if sys.platform == "darwin":
            return _apply_mac(enabled)
    except Exception:
        return False
    return False


def _apply_windows(enabled: bool) -> bool:
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        if enabled:
            winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, _VALUE_NAME)
            except FileNotFoundError:
                pass
    return True


def _apply_mac(enabled: bool) -> bool:
    if not enabled:
        _PLIST_PATH.unlink(missing_ok=True)
        return True
    _PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    python = sys.executable
    _PLIST_PATH.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.claude-halo</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/open</string>
    <string>-a</string><string>Terminal</string>
    <string>{python}</string>
  </array>
  <key>RunAtLoad</key><true/>
</dict></plist>
""",
        encoding="utf-8",
    )
    return True
