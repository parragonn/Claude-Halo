"""Premier plan macOS (Apple Silicon) : activer l'app terminal qui nous héberge.

On remonte l'arbre des processus jusqu'au premier ancêtre qui est une vraie
application GUI (NSRunningApplication, politique d'activation « regular »)
— Terminal.app, iTerm2, WezTerm, Alacritty, kitty… — puis on l'active en
ignorant les autres apps.

ÉCRIT MAIS NON TESTÉ sur cette machine de dev (Windows) : type-checké et
défensif ; à valider sur un Mac (la permission micro de l'OS, elle, est
demandée par PortAudio au premier accès).
"""

from __future__ import annotations

from collections.abc import Callable


class MacWindowManager:
    def __init__(self, mode_provider: Callable[[], str]) -> None:
        self._mode = mode_provider  # "always" | "unfocused"

    def bring_to_foreground(self) -> bool:
        try:
            import psutil
            from AppKit import (
                NSApplicationActivateIgnoringOtherApps,
                NSRunningApplication,
            )

            for process in psutil.Process().parents():
                if process.name().lower() in ("launchd", "kernel_task"):
                    break
                application = NSRunningApplication.runningApplicationWithProcessIdentifier_(
                    process.pid
                )
                if application is None or application.activationPolicy() != 0:
                    continue  # 0 = NSApplicationActivationPolicyRegular (vraie app GUI)
                if self._mode() == "unfocused" and application.isActive():
                    return True
                return bool(
                    application.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
                )
        except Exception:
            return False
        return False
