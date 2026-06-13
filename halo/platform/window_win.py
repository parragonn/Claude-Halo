"""Premier plan Windows : retrouver la fenêtre du terminal hôte et l'activer.

Sous Windows Terminal, GetConsoleWindow() renvoie une pseudo-fenêtre invisible :
on remonte alors l'arbre des processus (psutil) jusqu'à l'hôte réel (Windows
Terminal, VS Code, Alacritty, WezTerm…) et on prend sa fenêtre top-level
visible. SetForegroundWindow est restreint quand le processus n'a pas le
focus : contournement par frappe ALT synthétique, repli AttachThreadInput.
Tout échec est silencieux (False) — jamais d'exception qui remonte.
"""

from __future__ import annotations

from collections.abc import Callable

_EXCLUDED_PARENTS = {"explorer.exe", "services.exe", "svchost.exe", "wininit.exe"}


class WindowsWindowManager:
    def __init__(self, mode_provider: Callable[[], str]) -> None:
        self._mode = mode_provider  # "always" | "unfocused"
        self._hwnd: int | None = None

    def bring_to_foreground(self) -> bool:
        try:
            import win32gui

            hwnd = self._resolve()
            if hwnd is None:
                return False
            if self._mode() == "unfocused" and win32gui.GetForegroundWindow() == hwnd:
                return True  # déjà au premier plan : on ne s'impose pas
            return self._activate(hwnd)
        except Exception:
            return False

    # ── découverte de la fenêtre hôte ────────────────────────────────────────

    def _resolve(self) -> int | None:
        import win32gui

        if self._hwnd is not None and win32gui.IsWindow(self._hwnd):
            return self._hwnd
        self._hwnd = self._find_host_window()
        return self._hwnd

    def _find_host_window(self) -> int | None:
        import ctypes

        import win32gui

        console = ctypes.windll.kernel32.GetConsoleWindow()
        if console and win32gui.IsWindowVisible(console):
            return int(console)  # conhost classique

        import psutil

        try:
            parents = psutil.Process().parents()
        except Exception:
            return None
        for process in parents:
            try:
                if process.name().lower() in _EXCLUDED_PARENTS:
                    break
                hwnd = self._top_window_of_pid(process.pid)
            except Exception:
                continue
            if hwnd is not None:
                return hwnd
        return None

    @staticmethod
    def _top_window_of_pid(pid: int) -> int | None:
        import win32gui
        import win32process

        found: list[int] = []

        def probe(hwnd: int, _arg: object) -> bool:
            if not win32gui.IsWindowVisible(hwnd) or not win32gui.GetWindowText(hwnd):
                return True
            _thread, window_pid = win32process.GetWindowThreadProcessId(hwnd)
            if window_pid == pid:
                found.append(hwnd)
                return False
            return True

        try:
            win32gui.EnumWindows(probe, None)
        except Exception:
            pass  # EnumWindows s'arrête par exception quand le callback rend False
        return found[0] if found else None

    # ── activation ───────────────────────────────────────────────────────────

    @staticmethod
    def _activate(hwnd: int) -> bool:
        import win32api
        import win32con
        import win32gui
        import win32process

        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

        # Une frappe ALT synthétique lève la restriction anti-vol de focus.
        win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        finally:
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)

        if win32gui.GetForegroundWindow() == hwnd:
            return True

        # Repli : se rattacher à la file d'entrée du thread au premier plan.
        try:
            foreground = win32gui.GetForegroundWindow()
            target_thread, _pid = win32process.GetWindowThreadProcessId(foreground)
            current_thread = win32api.GetCurrentThreadId()
            win32process.AttachThreadInput(target_thread, current_thread, True)
            try:
                win32gui.BringWindowToTop(hwnd)
                win32gui.SetForegroundWindow(hwnd)
            finally:
                win32process.AttachThreadInput(target_thread, current_thread, False)
        except Exception:
            pass
        return bool(win32gui.GetForegroundWindow() == hwnd)
