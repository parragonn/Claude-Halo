"""Valeurs par défaut de Claude Halo."""

from __future__ import annotations

# Claude / IA
DEFAULT_BACKEND = "api"  # api | claude_code (abonnement Pro/Max via la CLI)
DEFAULT_MODEL = "claude-opus-4-8"
DEFAULT_EFFORT = "medium"  # off | low | medium | high
DEFAULT_SYSTEM_PROMPT = ""
DEFAULT_LANGUAGE = "fr"  # fr | en | auto
DEFAULT_MAX_TOKENS = 4096

# Voix
DEFAULT_WAKE_PHRASE = "Claude, aide-moi"
DEFAULT_MIC_DEVICE = "default"
DEFAULT_SENSITIVITY = 0.6
DEFAULT_STT_MODEL = "small"  # tiny | small | medium
DEFAULT_STT_DEVICE = "auto"  # auto | cuda | cpu
DEFAULT_SILENCE_TIMEOUT_S = 3.0
DEFAULT_LEXICON = ""  # termes techniques de l'utilisateur (franglais autorisé)
DEFAULT_CALIBRATED = False  # l'assistant de calibration a-t-il déjà tourné ?
DEFAULT_NOISE_FLOOR = 0.0  # plancher de bruit mesuré (0 = non calibré → défaut VAD)
DEFAULT_CALIBRATED_GAIN = 1.0  # gain de normalisation mesuré (1 = neutre)

# Apparence
DEFAULT_THEME = "auto"  # auto | dark | light
DEFAULT_ACCENT = "#8b5cf6"
DEFAULT_REVEAL = "fade"  # fade | typewriter | instant
DEFAULT_REDUCED_MOTION = False
DEFAULT_DENSITY = "comfortable"  # comfortable | compact

# Système
DEFAULT_FOREGROUND_MODE = "always"  # always | unfocused
DEFAULT_IDLE_RETURN_S = 180.0
DEFAULT_AUTOSTART = False
DEFAULT_HISTORY_ENABLED = False
