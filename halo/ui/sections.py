"""Construction déclarative du tableau de bord : réglages → sections de lignes.

Les actions encore non câblées (micro, client Claude, historique) affichent un
toast sobre indiquant le jalon — remplacées au fur et à mesure.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from halo.ai import catalog
from halo.ui.theme import ACCENT_PRESETS
from halo.ui.widgets.config_panel import Section
from halo.ui.widgets.rows import ActionRow, ChoiceRow, EditRow, NumericRow, ToggleRow

if TYPE_CHECKING:
    from halo.ui.tui_app import HaloApp

BACKEND_CHOICES = [
    ("api", "API Anthropic · clé & crédits"),
    ("claude_code", "Claude Code · abonnement Pro/Max"),
]
EFFORT_CHOICES = [
    ("off", "désactivé"),
    ("low", "faible"),
    ("medium", "moyen"),
    ("high", "élevé"),
]
LANGUAGE_CHOICES = [("fr", "français"), ("en", "anglais"), ("auto", "langue de la question")]
LENGTH_CHOICES = [
    ("1024", "courte · ≈1k tokens"),
    ("4096", "moyenne · ≈4k tokens"),
    ("16000", "longue · ≈16k tokens"),
]
STT_CHOICES = [
    ("tiny", "tiny · le plus rapide"),
    ("small", "small · recommandé"),
    ("medium", "medium · précision max"),
]
DEVICE_CHOICES = [
    ("auto", "auto · GPU si disponible"),
    ("cuda", "GPU (CUDA)"),
    ("cpu", "CPU"),
]
THEME_CHOICES = [("auto", "auto (détecté)"), ("dark", "sombre"), ("light", "clair")]
REVEAL_CHOICES = [
    ("fade", "fondu"),
    ("typewriter", "machine à écrire"),
    ("instant", "instantané"),
]
DENSITY_CHOICES = [("comfortable", "confortable"), ("compact", "compacte")]
FOREGROUND_CHOICES = [("always", "toujours"), ("unfocused", "seulement si non focus")]


def _shorten(text: str, width: int = 30) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 1] + "…"


def build_sections(app: HaloApp) -> list[Section]:
    s = app.settings
    secrets = app.secrets

    # ── Claude / IA ──────────────────────────────────────────────────────────
    def set_backend(v: str) -> None:
        s.ai.backend = v

    def set_model(v: str) -> None:
        s.ai.model = v

    def set_effort(v: str) -> None:
        s.ai.effort = v

    def set_language(v: str) -> None:
        s.ai.language = v

    def set_max_tokens(v: str) -> None:
        s.ai.max_tokens = int(v)

    def set_system_prompt(v: str) -> None:
        s.ai.system_prompt = v.strip()

    def api_key_display() -> str:
        return "●●●●●●●●  configurée" if secrets.get_api_key() else "non configurée"

    def set_api_key(v: str) -> None:
        v = v.strip()
        if not v:
            secrets.clear_api_key()
            app.notify("Clé d'API retirée du trousseau.")
        elif secrets.set_api_key(v):
            app.notify("Clé enregistrée dans le trousseau de l'OS.")
        else:
            app.notify("Trousseau indisponible — clé non enregistrée.", severity="warning")

    claude_ia = Section(
        "CLAUDE / IA",
        [
            ChoiceRow("Source des réponses", BACKEND_CHOICES, lambda: s.ai.backend, set_backend),
            ChoiceRow("Modèle", catalog.choices(), lambda: s.ai.model, set_model),
            ChoiceRow("Effort de réflexion", EFFORT_CHOICES, lambda: s.ai.effort, set_effort),
            EditRow(
                "Clé d'API",
                "Clé d'API Anthropic (stockée dans le trousseau)",
                api_key_display,
                lambda: "",
                set_api_key,
                mask=True,
                placeholder="sk-ant-…",
            ),
            ActionRow("Tester la connexion", app.test_connection, hint="vérifier clé & modèle"),
            EditRow(
                "System prompt",
                "System prompt / persona (optionnel)",
                lambda: _shorten(s.ai.system_prompt) or "aucun",
                lambda: s.ai.system_prompt,
                set_system_prompt,
                multiline=True,
            ),
            ChoiceRow("Langue de réponse", LANGUAGE_CHOICES, lambda: s.ai.language, set_language),
            ChoiceRow("Longueur max", LENGTH_CHOICES, lambda: str(s.ai.max_tokens), set_max_tokens),
        ],
    )

    # ── Voix ─────────────────────────────────────────────────────────────────
    def set_wake(v: str) -> None:
        if v.strip():
            s.voice.wake_phrase = v.strip()

    def set_mic(v: str) -> None:
        s.voice.mic_device = v
        app.restart_voice_engine()

    def set_sensitivity(v: float) -> None:
        s.voice.sensitivity = round(v, 2)
        app.restart_voice_engine()

    def set_stt_device(v: str) -> None:
        s.voice.stt_device = v
        app.restart_voice_engine()

    def set_stt(v: str) -> None:
        s.voice.stt_model = v
        if app.models_missing():
            app.notify(
                f"Le modèle « {v} » n'est pas encore local — lance « Modèles vocaux » "
                "ci-dessous pour le télécharger.",
                title="Voix",
                severity="warning",
            )

    def set_silence(v: float) -> None:
        s.voice.silence_timeout_s = v

    def set_lexicon(v: str) -> None:
        s.voice.lexicon = " ".join(v.split())

    voix = Section(
        "VOIX",
        [
            EditRow(
                "Phrase d'activation",
                "Phrase d'activation (wake word)",
                lambda: f"« {s.voice.wake_phrase} »",
                lambda: s.voice.wake_phrase,
                set_wake,
            ),
            ChoiceRow("Micro", app.microphone_choices(), lambda: s.voice.mic_device, set_mic),
            NumericRow(
                "Sensibilité",
                lambda: s.voice.sensitivity,
                set_sensitivity,
                0.1,
                0.95,
                0.05,
                lambda v: f"{round(v * 100)} %",
            ),
            ChoiceRow("Modèle STT (Whisper)", STT_CHOICES, lambda: s.voice.stt_model, set_stt),
            ChoiceRow(
                "Accélération STT", DEVICE_CHOICES, lambda: s.voice.stt_device, set_stt_device
            ),
            EditRow(
                "Vocabulaire technique",
                "Termes que tu dictes souvent (franglais bienvenu)",
                lambda: _shorten(s.voice.lexicon) or "lexique de base",
                lambda: s.voice.lexicon,
                set_lexicon,
                placeholder="Rust, Textual, uv, mypy…",
            ),
            NumericRow(
                "Silence fin de question",
                lambda: s.voice.silence_timeout_s,
                set_silence,
                1.0,
                8.0,
                0.5,
                lambda v: f"{v:.1f} s".replace(".", ","),
            ),
            ActionRow(
                "Calibrer le micro",
                app.run_calibration,
                hint=lambda: "✓ calibré" if s.voice.calibrated else "recommandé",
            ),
            ActionRow("Test du micro", app.test_microphone, hint="VU-mètre en direct"),
            ActionRow("Modèles vocaux", app.download_models, hint=app.voice_models_label),
        ],
    )

    # ── Apparence ────────────────────────────────────────────────────────────
    def set_theme(v: str) -> None:
        s.appearance.theme = v
        app.apply_appearance()

    def set_accent(v: str) -> None:
        s.appearance.accent = v
        app.apply_appearance()

    def set_reveal(v: str) -> None:
        s.appearance.reveal = v

    def set_reduced(v: bool) -> None:
        s.appearance.reduced_motion = v
        app.apply_motion()

    def set_density(v: str) -> None:
        s.appearance.density = v
        app.apply_density()

    apparence = Section(
        "APPARENCE",
        [
            ChoiceRow("Thème", THEME_CHOICES, lambda: s.appearance.theme, set_theme),
            ChoiceRow(
                "Couleur d'accent", list(ACCENT_PRESETS), lambda: s.appearance.accent, set_accent
            ),
            ChoiceRow(
                "Animation de réponse", REVEAL_CHOICES, lambda: s.appearance.reveal, set_reveal
            ),
            ToggleRow("Reduced motion", lambda: s.appearance.reduced_motion, set_reduced),
            ChoiceRow("Densité", DENSITY_CHOICES, lambda: s.appearance.density, set_density),
        ],
    )

    # ── Système ──────────────────────────────────────────────────────────────
    def set_foreground(v: str) -> None:
        s.system.foreground_mode = v

    def set_idle_return(v: float) -> None:
        s.system.idle_return_s = v

    def set_autostart(v: bool) -> None:
        s.system.autostart = v
        app.apply_autostart()

    def set_history(v: bool) -> None:
        s.system.history_enabled = v

    systeme = Section(
        "SYSTÈME",
        [
            ChoiceRow(
                "Premier plan", FOREGROUND_CHOICES, lambda: s.system.foreground_mode, set_foreground
            ),
            NumericRow(
                "Retour au repos",
                lambda: s.system.idle_return_s,
                set_idle_return,
                30.0,
                600.0,
                30.0,
                lambda v: f"{int(v)} s",
            ),
            ToggleRow("Lancement au démarrage", lambda: s.system.autostart, set_autostart),
            ToggleRow("Historique des sessions", lambda: s.system.history_enabled, set_history),
            ActionRow("Effacer l'historique", app.clear_history, hint="tout effacer"),
        ],
    )

    return [claude_ia, voix, apparence, systeme]
