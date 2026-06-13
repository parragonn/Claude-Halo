"""Intégration bout-en-bout avec les faux adapters : F2 → écoute → parole
simulée → transcription → réponse en écho → fil de session → retour accueil."""

from __future__ import annotations

import threading
import time

from halo.ai.fake import EchoProvider
from halo.audio.fake import FakeVoiceEngine
from halo.config.settings import Settings
from halo.coordinator import Coordinator, make_emitter
from halo.core.models import Phase
from halo.ui.screens.idle import IdleScreen
from halo.ui.screens.session import SessionScreen
from halo.ui.terminal_probe import TerminalColors
from halo.ui.tui_app import HaloApp

QUESTION = "Quelle heure est-il ?"


class FakeSecrets:
    def get_api_key(self) -> str | None:
        return None

    def set_api_key(self, value: str) -> bool:
        return True

    def clear_api_key(self) -> bool:
        return True


def build_app(speed: float = 24.0) -> tuple[HaloApp, FakeVoiceEngine]:
    settings = Settings()
    app = HaloApp(
        settings=settings,
        secrets=FakeSecrets(),
        terminal_colors=TerminalColors(None, None, True),
        save=lambda s: None,
    )
    emit = make_emitter(app)
    engine = FakeVoiceEngine(emit, question=QUESTION, speed=speed)
    app.coordinator = Coordinator(
        app=app,
        settings=settings,
        engine=engine,
        provider=EchoProvider(delay=0.02),
        window=None,
    )
    return app, engine


async def wait_for(pilot, predicate, timeout: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await pilot.pause(0.05)
    return predicate()


async def test_full_voice_loop_with_fakes() -> None:
    app, _engine = build_app()
    async with app.run_test(size=(110, 36)) as pilot:
        assert app.coordinator is not None
        await pilot.press("f2")
        await pilot.pause()
        assert isinstance(app.screen, SessionScreen)
        # (pas d'assertion sur la phase ici : à vitesse x24 le script peut déjà
        # avoir dépassé LISTENING — le test d'annulation couvre cette phase)

        ok = await wait_for(
            pilot, lambda: app.coordinator.machine.state.phase is Phase.SESSION_IDLE
        )
        assert ok, f"état final inattendu : {app.coordinator.machine.state}"

        session = app.coordinator.session
        assert session.turns[0].question == QUESTION
        assert session.turns[0].completed
        assert "entendu" in session.turns[0].answer

        await pilot.press("escape")
        await pilot.pause()
        assert app.coordinator.machine.state.phase is Phase.IDLE
        assert isinstance(app.screen, IdleScreen)
        assert app.coordinator.session.is_empty


async def test_escape_cancels_listening_back_to_home() -> None:
    # Vitesse réelle : l'écoute dure ~2 s, l'Échap tombe pendant LISTENING.
    app, _engine = build_app(speed=1.0)
    async with app.run_test(size=(110, 36)) as pilot:
        assert app.coordinator is not None
        await pilot.press("f2")
        await pilot.pause()
        assert app.coordinator.machine.state.phase is Phase.LISTENING
        await pilot.press("escape")
        await pilot.pause()
        assert app.coordinator.machine.state.phase is Phase.IDLE
        assert isinstance(app.screen, IdleScreen)


async def test_followup_turn_then_session_buttons() -> None:
    app, engine = build_app()
    async with app.run_test(size=(110, 36)) as pilot:
        assert app.coordinator is not None
        coordinator = app.coordinator
        await pilot.press("f2")
        assert await wait_for(
            pilot, lambda: coordinator.machine.state.phase is Phase.SESSION_IDLE
        )

        # Question suivante : « Claude, … » — l'orbe reste parquée, le fil grandit.
        engine.trigger_wake("")
        assert await wait_for(
            pilot,
            lambda: coordinator.machine.state.phase is Phase.SESSION_IDLE
            and len(coordinator.session.turns) == 2,
        )
        screen = app.screen
        assert isinstance(screen, SessionScreen)
        assert screen._thread.turn_count == 2

        # tab → boutons ; ↓ + Entrée = New session (fil vidé, toujours en session)
        await pilot.press("tab")
        await pilot.pause()
        assert screen._buttons.active, "tab doit activer les boutons"
        await pilot.press("down", "enter")
        await pilot.pause()
        assert coordinator.machine.state.phase is Phase.SESSION_IDLE
        assert coordinator.session.is_empty
        assert screen._thread.turn_count == 0

        # ↑ + Entrée = Back to home
        await pilot.press("up", "enter")
        await pilot.pause()
        assert coordinator.machine.state.phase is Phase.IDLE
        assert isinstance(app.screen, IdleScreen)


async def test_reduced_motion_freezes_orb_and_reveals_instantly() -> None:
    app, _engine = build_app()
    app.settings.appearance.reduced_motion = True
    app.apply_motion()
    async with app.run_test(size=(110, 36)) as pilot:
        assert app.coordinator is not None
        assert not app.motion.enabled
        await pilot.press("f2")
        assert await wait_for(
            pilot, lambda: app.coordinator.machine.state.phase is Phase.SESSION_IDLE
        )
        screen = app.screen
        assert isinstance(screen, SessionScreen)
        from halo.ui.widgets.orb_physics import OrbMode

        assert screen.orb.physics.mode is OrbMode.STATIC
        assert screen._thread.turn_count == 1


async def test_wake_event_from_engine_thread_opens_session() -> None:
    app, engine = build_app()
    async with app.run_test(size=(110, 36)) as pilot:
        assert app.coordinator is not None
        thread = threading.Thread(target=engine.trigger_wake, args=("quelle heure",))
        thread.start()
        thread.join()
        ok = await wait_for(
            pilot, lambda: app.coordinator.machine.state.phase is not Phase.IDLE, timeout=4.0
        )
        assert ok
        assert isinstance(app.screen, SessionScreen)
