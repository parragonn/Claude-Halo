"""Assistant de calibration : pipeline scripté → application aux réglages."""

from __future__ import annotations

import time

from halo.audio.calibration import CalibrationResult
from halo.config.settings import Settings
from halo.ui.terminal_probe import TerminalColors
from halo.ui.tui_app import HaloApp
from halo.ui.widgets.calibration_modal import CalibrationModal


class FakeSecrets:
    def get_api_key(self) -> str | None:
        return None

    def set_api_key(self, value: str) -> bool:
        return True

    def clear_api_key(self) -> bool:
        return True


class FakeCalibrator:
    """Rejoue le pipeline sans toucher au micro."""

    def __init__(self, result: CalibrationResult, transcript: str) -> None:
        self._result = result
        self._transcript = transcript

    def run(self, *, on_phase, on_level, on_done, on_error) -> None:  # type: ignore[no-untyped-def]
        on_phase("noise")
        on_phase("voice")
        on_level(0.6)
        on_phase("transcribe")
        on_done(self._result, self._transcript)


def make_app() -> HaloApp:
    app = HaloApp(
        settings=Settings(),
        secrets=FakeSecrets(),
        terminal_colors=TerminalColors(None, None, True),
        save=lambda s: None,
    )
    result = CalibrationResult(
        noise_rms=0.002,
        voice_rms=0.05,
        snr=25.0,
        sensitivity=0.62,
        gain=1.5,
        quality="excellent",
        message="Micro excellent.",
    )
    app.calibrator_factory = lambda: FakeCalibrator(result, "comment apprendre Rust")  # type: ignore[assignment]
    return app


async def wait_until(pilot, predicate, timeout: float = 4.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await pilot.pause(0.05)
    return predicate()


async def test_calibration_applies_to_settings() -> None:
    app = make_app()
    async with app.run_test(size=(104, 40)) as pilot:
        app.run_calibration()
        await pilot.pause()
        assert isinstance(app.screen, CalibrationModal)

        await pilot.press("enter")  # intro → lance le pipeline (thread)
        modal = app.screen
        assert isinstance(modal, CalibrationModal)
        assert await wait_until(pilot, lambda: modal._stage == "result")

        await pilot.press("enter")  # applique
        await pilot.pause()
        assert not isinstance(app.screen, CalibrationModal)
        assert app.settings.voice.calibrated is True
        assert app.settings.voice.sensitivity == 0.62
        assert app.settings.voice.calibrated_gain == 1.5
        assert app.settings.voice.noise_floor == 0.002


async def test_calibration_cancel_keeps_defaults() -> None:
    app = make_app()
    async with app.run_test(size=(104, 40)) as pilot:
        app.run_calibration()
        await pilot.pause()
        await pilot.press("escape")  # annule depuis l'intro
        await pilot.pause()
        assert not isinstance(app.screen, CalibrationModal)
        assert app.settings.voice.calibrated is False
