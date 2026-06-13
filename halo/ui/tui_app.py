"""L'application Textual : thème adaptatif, écrans, routage des événements.

Reçoit tous ses adapters de la composition root (halo.app) ; le coordinateur
lui transmet chaque événement du domaine via `on_domain_event`, qu'elle route
vers l'écran concerné. Aucune logique de domaine ici.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, ClassVar

from textual.app import App
from textual.binding import Binding, BindingType

from halo.ai import catalog
from halo.ai.ports import ConnectionReport
from halo.config.settings import Settings
from halo.core import events as ev
from halo.core.models import Command, FailureKind, MachineState, Phase, Turn
from halo.platform.accel import AccelReport
from halo.platform.ports import SecretStore
from halo.ui.animation import MotionPolicy
from halo.ui.screens.idle import IdleScreen
from halo.ui.screens.session import SessionScreen
from halo.ui.terminal_probe import TerminalColors
from halo.ui.theme import DEFAULT_ACCENT, HaloPalette, build_theme, derive_palette
from halo.ui.widgets.voice_modals import DownloadModal, MicTestModal

if TYPE_CHECKING:
    from collections.abc import Callable as _Callable

    from halo.audio.mic_calibrator import MicCalibrator
    from halo.coordinator import Coordinator, DomainEventMessage

_FAILURE_TEXT: dict[FailureKind, str] = {
    FailureKind.AUTH: "clé d'API invalide ou absente — Réglages ▸ Claude / IA",
    FailureKind.BILLING: "crédits Anthropic épuisés — recharge sur console.anthropic.com ▸ Billing",
    FailureKind.OFFLINE: "connexion impossible — vérifie le réseau",
    FailureKind.RATE_LIMIT: "limite de débit atteinte — patiente un instant",
    FailureKind.OVERLOADED: "service momentanément surchargé — réessaie",
    FailureKind.TIMEOUT: "délai dépassé — réessaie",
    FailureKind.BAD_REQUEST: "requête refusée par l'API",
    FailureKind.UNKNOWN: "erreur inattendue",
}

_FAULT_TEXT = {
    "NO_MIC": "aucun micro détecté — F2 pour parler au clavier",
    "PERMISSION_DENIED": "accès micro refusé (Paramètres › Confidentialité)",
    "DEVICE_LOST": "micro débranché — rebranche puis rouvre l'app",
    "ENGINE_ERROR": "moteur vocal en erreur — F2 reste disponible",
}


class HaloApp(App[None]):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("f2", "manual_wake", "Parler", priority=True),
    ]

    def __init__(
        self,
        *,
        settings: Settings,
        secrets: SecretStore,
        terminal_colors: TerminalColors,
        save: Callable[[Settings], None],
        orb_demo: bool = False,
        mic_choices: Callable[[], list[tuple[str, str]]] | None = None,
        models_missing: Callable[[], list[str]] | None = None,
        download_model: Callable[[str, Callable[[int, int], None]], None] | None = None,
        connection_tester: Callable[[str, str], Awaitable[ConnectionReport]] | None = None,
        code_tester: Callable[[], Awaitable[ConnectionReport]] | None = None,
        autostart_apply: Callable[[bool], bool] | None = None,
        first_run: bool = False,
        accel: AccelReport | None = None,
    ) -> None:
        super().__init__()
        self._orb_demo = orb_demo
        self.settings = settings
        self.secrets = secrets
        self._detected = terminal_colors
        self._save = save
        self._mic_choices = mic_choices or (lambda: [("default", "périphérique par défaut")])
        self._models_missing = models_missing or (lambda: [])
        self._download_model = download_model or (lambda size, progress: None)
        self._connection_tester = connection_tester
        self._code_tester = code_tester
        self._autostart_apply = autostart_apply
        self._first_run = first_run
        self.accel = accel
        self.coordinator: Coordinator | None = None
        self.calibrator_factory: _Callable[[], MicCalibrator] | None = None
        self.motion = MotionPolicy.from_settings(settings.appearance.reduced_motion)
        self.palette = derive_palette(self._effective_colors(), settings.appearance.accent)
        self.voice_status = "démarrage…"
        self.mic_level_sink: Callable[[float], None] | None = None
        self._session_screen: SessionScreen | None = None
        self._voice_ready = False
        self._voice_restart_timer: object | None = None

    # ── cycle de vie ─────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self.apply_appearance()
        if self._orb_demo:
            from halo.ui.screens.orb_demo import OrbDemoScreen

            self.push_screen(OrbDemoScreen())
            return
        self.push_screen(IdleScreen())
        if self._first_run:
            from halo.ui.screens.onboarding import OnboardingScreen

            # Différé : laisse le thème/variables s'installer avant le parse CSS.
            self.call_after_refresh(lambda: self.push_screen(OnboardingScreen()))
        self.start_voice_engine()

    # ── moteur vocal ─────────────────────────────────────────────────────────

    def start_voice_engine(self) -> None:
        coordinator = self.coordinator
        if coordinator is None or coordinator.engine is None:
            self.set_voice_status("mode sans voix — F2 pour parler")
            return
        if self._models_missing():
            self.set_voice_status("modèles vocaux à télécharger — Réglages ▸ Voix")
            return
        if coordinator.engine.start():
            self._voice_ready = True
            self.set_voice_status(f"à l'écoute de « {self.settings.voice.wake_phrase} »")
            self._warn_if_gpu_unavailable()
        else:
            self.set_voice_status("micro indisponible — F2 pour parler")

    def _warn_if_gpu_unavailable(self) -> None:
        if (
            self.settings.voice.stt_device == "cuda"
            and self.accel is not None
            and not self.accel.cuda_ready
        ):
            self.notify(
                "GPU forcé mais CUDA indisponible → transcription sur CPU (plus lente). "
                "Relance « uv run --extra cuda halo », ou mets « Accélération STT » sur auto.",
                title="Accélération STT",
                severity="warning",
                timeout=8,
            )

    def restart_voice_engine(self) -> None:
        """Relance le moteur après un changement de micro/sensibilité — débouncé
        pour ne pas rouvrir le flux à chaque cran d'un réglage."""
        timer = self._voice_restart_timer
        if timer is not None:
            timer.stop()  # type: ignore[attr-defined]
        self._voice_restart_timer = self.set_timer(0.6, self._do_voice_restart)

    def _do_voice_restart(self) -> None:
        self._voice_restart_timer = None
        coordinator = self.coordinator
        if coordinator is None or coordinator.engine is None:
            return
        if self._voice_ready:
            coordinator.engine.stop()
            self._voice_ready = False
        self.start_voice_engine()

    def set_voice_status(self, text: str) -> None:
        self.voice_status = text
        for widget in self.query("ListeningStatus"):
            widget.refresh()

    # ── routage des événements du domaine ────────────────────────────────────

    def on_domain_event_message(self, message: DomainEventMessage) -> None:
        """Événement du domaine posté depuis un thread (voir make_emitter)."""
        if self.coordinator is not None:
            self.coordinator.handle(message.event)

    def on_domain_event(
        self, event: ev.Event, previous: MachineState, state: MachineState
    ) -> None:
        if isinstance(event, ev.AmplitudeChanged) and self.mic_level_sink is not None:
            self.mic_level_sink(event.level)
        if isinstance(event, ev.AudioFault):
            self._on_audio_fault(event)

        if previous.phase is Phase.IDLE and state.phase is not Phase.IDLE:
            if self._session_screen is None:
                self._session_screen = SessionScreen()
                self.push_screen(self._session_screen)
        if state.phase is Phase.IDLE:
            if self._session_screen is not None:
                self._session_screen = None
                self.pop_screen()
            return
        screen = self._session_screen
        if screen is not None and screen.is_mounted:
            if isinstance(event, ev.ResponseFailed):
                hint = f"  ({event.hint})" if event.hint else ""
                screen.show_failure(_FAILURE_TEXT[event.kind] + hint)
            screen.on_domain_event(event, state)

    def on_turn_started(self, turn: Turn) -> None:
        if self._session_screen is not None and self._session_screen.is_mounted:
            self._session_screen.on_turn_started(turn.question)

    def on_session_reset(self) -> None:
        if self._session_screen is not None and self._session_screen.is_mounted:
            self._session_screen.reset_thread()

    def coordinator_state(self) -> MachineState:
        return self.coordinator.machine.state if self.coordinator else MachineState()

    def dispatch_command(self, command: Command) -> None:
        if self.coordinator is not None:
            self.coordinator.handle(ev.UserCommand(command=command))

    def _on_audio_fault(self, fault: ev.AudioFault) -> None:
        message = _FAULT_TEXT.get(fault.kind.name, "souci audio")
        self.set_voice_status(message)
        self.notify(message, title="Audio", severity="warning", timeout=5)

    # ── apparence ────────────────────────────────────────────────────────────

    def get_theme_variable_defaults(self) -> dict[str, str]:
        """Valeurs par défaut des variables Halo : le CSS des widgets doit se
        compiler quel que soit l'ordre d'application du thème (le vrai terminal
        et le mode test ne montent pas les écrans dans le même ordre)."""
        palette: HaloPalette | None = getattr(self, "palette", None)
        if palette is None:
            palette = derive_palette(TerminalColors(None, None, True), DEFAULT_ACCENT)
        return {
            "ansi-background": "ansi_default",
            "ansi-foreground": "ansi_default",
            "halo-accent": palette.accent,
            "halo-accent-soft": palette.accent_soft,
            "halo-accent-deep": palette.accent_deep,
            "halo-secondary": palette.text_secondary,
            "halo-dim": palette.text_dim,
            "halo-border": palette.border,
        }

    def _effective_colors(self) -> TerminalColors:
        override = self.settings.appearance.theme
        if override not in ("dark", "light") or (override == "dark") == self._detected.dark:
            return self._detected
        return TerminalColors(None, None, override == "dark")

    def apply_appearance(self) -> None:
        self.palette = derive_palette(self._effective_colors(), self.settings.appearance.accent)
        theme = build_theme(self.palette)
        self.register_theme(theme)
        if self.theme == theme.name:
            self.refresh_css()
        else:
            self.theme = theme.name
        if self.screen_stack:
            self.screen.query("*").refresh()

    def apply_motion(self) -> None:
        self.motion = MotionPolicy.from_settings(self.settings.appearance.reduced_motion)

    def apply_density(self) -> None:
        compact = self.settings.appearance.density == "compact"
        for screen in self.screen_stack:
            screen.set_class(compact, "compact")

    # ── réglages & actions du tableau de bord ────────────────────────────────

    def persist_settings(self) -> None:
        self._save(self.settings)

    def microphone_choices(self) -> list[tuple[str, str]]:
        try:
            return self._mic_choices()
        except Exception:
            return [("default", "périphérique par défaut")]

    def models_missing(self) -> list[str]:
        try:
            return self._models_missing()
        except Exception:
            return []

    @property
    def model_downloader(self) -> Callable[[str, Callable[[int, int], None]], None]:
        return self._download_model

    def voice_models_label(self) -> str:
        missing = self.models_missing()
        return "prêts ✓" if not missing else f"télécharger : {', '.join(missing)}"

    def download_models(self) -> None:
        missing = self.models_missing()
        if not missing:
            self.notify("Modèles vocaux déjà prêts ✓", title="Voix")
            return

        def done(ok: bool | None) -> None:
            if ok:
                self.notify("Modèles téléchargés ✓", title="Voix")
                self.start_voice_engine()

        self.push_screen(DownloadModal(missing, self._download_model), done)

    def test_connection(self) -> None:
        if self.settings.ai.backend == "claude_code":
            self._test_claude_code()
            return
        tester = self._connection_tester
        if tester is None:
            self.notify("Test de connexion indisponible dans ce mode.", title="Connexion")
            return
        api_key = self.secrets.get_api_key()
        if not api_key:
            self.notify(
                "Configure d'abord la clé d'API (Réglages ▸ Claude / IA).",
                title="Connexion",
                severity="warning",
            )
            return
        model = self.settings.ai.model
        self.notify("Vérification…", title="Connexion", timeout=2)

        async def job() -> None:
            report = await tester(api_key, model)
            if report.ok:
                if report.models:
                    catalog.update_from_api(report.models)
                    if isinstance(self.screen, IdleScreen):
                        self.screen.refresh(recompose=True)
                self.notify(report.message, title="Connexion")
            else:
                self.notify(report.message, title="Connexion", severity="error")

        self.run_worker(job(), exclusive=True)

    def _test_claude_code(self) -> None:
        tester = self._code_tester
        if tester is None:
            self.notify("Vérification Claude Code indisponible dans ce mode.", title="Connexion")
            return
        self.notify("Vérification de Claude Code…", title="Connexion", timeout=2)

        async def job() -> None:
            report = await tester()
            if report.ok:
                self.notify(report.message, title="Connexion")
            else:
                self.notify(report.message, title="Connexion", severity="error")

        self.run_worker(job(), exclusive=True)

    def test_microphone(self) -> None:
        if not self._voice_ready:
            self.notify(
                "Moteur vocal non démarré (modèles ou micro manquants).",
                title="Test du micro",
                severity="warning",
            )
            return
        self.push_screen(MicTestModal())

    def run_calibration(self) -> None:
        """Assistant de calibration : met le moteur en pause (accès micro
        exclusif), mesure, applique sensibilité+gain+plancher, redémarre."""
        factory = self.calibrator_factory
        if factory is None:
            self.notify("Calibration indisponible dans ce mode.", title="Calibration")
            return
        if self.models_missing():
            self.notify(
                "Télécharge d'abord les modèles vocaux (Réglages ▸ Voix).",
                title="Calibration",
                severity="warning",
            )
            return
        from halo.ui.widgets.calibration_modal import CalibrationModal

        coordinator = self.coordinator
        if coordinator is not None and coordinator.engine is not None:
            coordinator.engine.stop()  # libère micro + GPU (idempotent)
            self._voice_ready = False
        calibrator = factory()

        def done(result: object | None) -> None:
            if result is not None:
                v = self.settings.voice
                v.sensitivity = result.sensitivity  # type: ignore[attr-defined]
                v.calibrated_gain = result.gain  # type: ignore[attr-defined]
                v.noise_floor = round(result.noise_rms, 5)  # type: ignore[attr-defined]
                v.calibrated = True
                self.persist_settings()
                self._refresh_dashboard()
                self.notify(
                    f"Micro calibré : {result.quality}.",  # type: ignore[attr-defined]
                    title="Calibration",
                )
            self.start_voice_engine()  # relance l'écoute

        self.push_screen(
            CalibrationModal(calibrator, self.settings.voice.wake_phrase), done
        )

    def _refresh_dashboard(self) -> None:
        if isinstance(self.screen, IdleScreen):
            self.screen.refresh(recompose=True)

    def apply_autostart(self) -> None:
        if self._autostart_apply is None:
            return
        if not self._autostart_apply(self.settings.system.autostart):
            self.notify(
                "Impossible d'appliquer le lancement au démarrage.",
                title="Système",
                severity="warning",
            )

    def clear_history(self) -> None:
        if self.coordinator is not None and self.coordinator.clear_history():
            self.notify("Historique effacé.", title="Historique")
        else:
            self.notify("Aucun historique à effacer.", title="Historique")

    def action_manual_wake(self) -> None:
        if self.coordinator is None:
            return
        if not self._voice_ready:
            reason = (
                "télécharge d'abord les modèles vocaux (Réglages ▸ Voix)"
                if self.models_missing()
                else "le micro n'a pas démarré — vérifie le périphérique (Réglages ▸ Voix)"
            )
            self.notify(
                f"L'écoute est inactive : {reason}.",
                title="Activation manuelle",
                severity="warning",
            )
        self.dispatch_command(Command.MANUAL_WAKE)
