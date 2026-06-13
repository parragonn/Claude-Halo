"""Fumée TUI : l'écran d'accueil monte, se pilote au clavier, persiste les réglages."""

from __future__ import annotations

from halo.config.settings import Settings
from halo.ui.terminal_probe import TerminalColors
from halo.ui.tui_app import HaloApp
from halo.ui.widgets.config_panel import ConfigPanel
from halo.ui.widgets.modals import EditModal


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


def make_app(saves: list[Settings]) -> HaloApp:
    return HaloApp(
        settings=Settings(),
        secrets=FakeSecrets(),
        terminal_colors=TerminalColors(None, None, True),
        save=saves.append,
    )


async def test_idle_screen_mounts_and_navigates() -> None:
    saves: list[Settings] = []
    app = make_app(saves)
    async with app.run_test(size=(104, 40)) as pilot:
        panel = app.screen.query_one(ConfigPanel)
        assert panel.has_focus
        assert panel.current_row is not None
        assert panel.current_row.label == "Source des réponses"

        await pilot.press("down", "down")
        assert panel.current_row.label == "Effort de réflexion"

        await pilot.press("right")
        assert app.settings.ai.effort == "high"
        assert saves, "tout changement est persisté immédiatement"

        await pilot.press("up")
        await pilot.press("right")
        assert app.settings.ai.model == "claude-fable-5"


async def test_api_key_modal_opens_and_cancels() -> None:
    saves: list[Settings] = []
    app = make_app(saves)
    async with app.run_test(size=(104, 40)) as pilot:
        panel = app.screen.query_one(ConfigPanel)
        await pilot.press("down", "down", "down")
        assert panel.current_row is not None
        assert panel.current_row.label == "Clé d'API"
        await pilot.press("enter")
        assert isinstance(app.screen, EditModal)
        await pilot.press("escape")
        assert not isinstance(app.screen, EditModal)


async def test_theme_switch_applies_live() -> None:
    saves: list[Settings] = []
    app = make_app(saves)
    async with app.run_test(size=(104, 40)) as pilot:
        assert app.theme == "halo-dark"
        app.settings.appearance.theme = "light"
        app.apply_appearance()
        await pilot.pause()
        assert app.theme == "halo-light"
        assert not app.palette.dark
