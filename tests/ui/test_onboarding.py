"""Onboarding : visible au premier lancement, Entrée matérialise la config."""

from __future__ import annotations

from halo.config.settings import Settings
from halo.ui.screens.idle import IdleScreen
from halo.ui.screens.onboarding import OnboardingScreen
from halo.ui.terminal_probe import TerminalColors
from halo.ui.tui_app import HaloApp


class FakeSecrets:
    def __init__(self) -> None:
        self.value: str | None = None

    def get_api_key(self) -> str | None:
        return self.value

    def set_api_key(self, value: str) -> bool:
        self.value = value
        return True

    def clear_api_key(self) -> bool:
        self.value = None
        return True


async def test_onboarding_then_enter_lands_on_dashboard() -> None:
    saves: list[Settings] = []
    app = HaloApp(
        settings=Settings(),
        secrets=FakeSecrets(),
        terminal_colors=TerminalColors(None, None, True),
        save=saves.append,
        first_run=True,
    )
    async with app.run_test(size=(104, 40)) as pilot:
        for _ in range(20):  # le push de l'onboarding est différé d'un refresh
            if isinstance(app.screen, OnboardingScreen):
                break
            await pilot.pause(0.02)
        assert isinstance(app.screen, OnboardingScreen)
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, IdleScreen)
        assert saves, "Entrée matérialise la config (l'onboarding ne revient plus)"


async def test_no_onboarding_on_regular_run() -> None:
    app = HaloApp(
        settings=Settings(),
        secrets=FakeSecrets(),
        terminal_colors=TerminalColors(None, None, True),
        save=lambda s: None,
        first_run=False,
    )
    async with app.run_test(size=(104, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, IdleScreen)
