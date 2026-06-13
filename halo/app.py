"""Composition root : câble tous les adapters et lance l'app.

Seul endroit du code autorisé à importer des implémentations concrètes
(trousseau, sonde terminal, moteur audio, fournisseur de réponses, OS).
"""

from __future__ import annotations

import argparse

from halo import __version__


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="halo",
        description="Claude Halo — assistant vocal Jarvis dans le terminal.",
    )
    parser.add_argument("--version", action="version", version=f"halo {__version__}")
    parser.add_argument(
        "--demo", action="store_true", help="parcours scripté sans micro ni clé API"
    )
    parser.add_argument(
        "--orb-demo", action="store_true", help="écran de mise au point de l'orbe"
    )
    return parser.parse_args()


def run() -> None:
    args = _parse_args()

    from halo.ai.claude_client import ClaudeClient, check_connection
    from halo.ai.claude_code_provider import ClaudeCodeProvider, check_claude_code
    from halo.ai.ports import ResponseProvider
    from halo.ai.switch import SwitchableProvider
    from halo.audio import whisper_models
    from halo.audio.capture import list_microphones
    from halo.audio.ports import VoiceEngine
    from halo.config.settings import config_path, load_settings, save_settings
    from halo.coordinator import Coordinator, make_emitter
    from halo.platform.accel import probe_accelerator
    from halo.platform.autostart import apply_autostart
    from halo.platform.keychain import KeyringSecretStore
    from halo.platform.ports import WindowManager
    from halo.ui.terminal_probe import detect_terminal_colors
    from halo.ui.tui_app import HaloApp

    first_run = not config_path().exists()
    settings = load_settings()
    if first_run and not args.demo and settings.voice.mic_device == "default":
        # Au tout premier lancement, viser un vrai micro plutôt que le défaut
        # système (souvent un bus virtuel type Voicemeeter sur les setups chargés).
        from halo.audio.capture import best_input_device

        settings.voice.mic_device = best_input_device()
    terminal_colors = detect_terminal_colors(settings.appearance.theme)
    secrets = KeyringSecretStore()
    accel = probe_accelerator()

    app = HaloApp(
        settings=settings,
        secrets=secrets,
        terminal_colors=terminal_colors,
        save=save_settings,
        orb_demo=args.orb_demo,
        mic_choices=list_microphones,
        models_missing=(lambda: [])
        if args.demo
        else (lambda: whisper_models.missing_sizes(settings.voice.stt_model)),
        download_model=whisper_models.download,
        connection_tester=check_connection,
        code_tester=check_claude_code,
        autostart_apply=apply_autostart,
        first_run=first_run and not args.orb_demo,
        accel=accel,
    )

    # Les threads du moteur (audio, stt) entrent dans la boucle UI par ici.
    emit = make_emitter(app)

    engine: VoiceEngine
    provider: ResponseProvider
    if args.demo:
        from halo.ai.fake import DemoProvider
        from halo.audio.fake import FakeVoiceEngine

        engine = FakeVoiceEngine(emit)
        provider = DemoProvider()
    else:
        from halo.audio.engine import SttVoiceEngine

        stt_engine = SttVoiceEngine(settings, emit, cuda_possible=accel.cuda_ready)
        engine = stt_engine
        provider = SwitchableProvider(
            settings,
            {
                "api": ClaudeClient(secrets.get_api_key),
                "claude_code": ClaudeCodeProvider(),
            },
        )

        from halo.audio.mic_calibrator import MicCalibrator

        app.calibrator_factory = lambda: MicCalibrator(settings, stt_engine.store)

    import sys

    window: WindowManager | None = None
    if sys.platform == "win32":
        from halo.platform.window_win import WindowsWindowManager

        window = WindowsWindowManager(lambda: settings.system.foreground_mode)
    elif sys.platform == "darwin":
        from halo.platform.window_mac import MacWindowManager

        window = MacWindowManager(lambda: settings.system.foreground_mode)

    from halo.config.history import HistoryStore

    app.coordinator = Coordinator(
        app=app,
        settings=settings,
        engine=engine,
        provider=provider,
        window=window,
        history=HistoryStore(),
    )
    app.run()
