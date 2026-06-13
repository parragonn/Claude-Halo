"""Construction de la commande de démarrage (partie pure)."""

from __future__ import annotations

from halo.platform.autostart import startup_command


def test_startup_command_prefers_windows_terminal() -> None:
    command = startup_command(python="C:\\venv\\python.exe", wt="C:\\apps\\wt.exe")
    assert command.startswith('"C:\\apps\\wt.exe"')
    assert '"C:\\venv\\python.exe" -m halo' in command


def test_startup_command_falls_back_to_console() -> None:
    command = startup_command(python="p.exe", wt="")
    assert command.startswith("cmd /c start")
    assert "-m halo" in command
