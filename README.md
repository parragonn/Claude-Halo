# ◆ Claude Halo

/!\ Projet vibe codé avec Claude Fable 5 & Opus 4.8 /!\

Un assistant vocal « Jarvis » qui vit dans ton terminal — silencieux en arrière-plan,
il s'éveille à la voix.

Dis **« Claude, aide-moi »** : le terminal passe au premier plan, une orbe de
micro-particules Braille s'anime au rythme de ta voix, ta question est transcrite
**localement** (Whisper), et la réponse de Claude arrive en Markdown streamé dans un
fil de conversation. Au repos : un tableau de bord de configuration complet,
navigable aux flèches.

Le tout respecte le thème de ton terminal (clair/sombre natifs, un seul accent
violet configurable), `NO_COLOR`, et le reduced-motion.

---

## Prérequis

- **Windows 10/11** (développé et testé) ou **macOS Apple Silicon** (adapters écrits,
  *non testés* — retours bienvenus) ;
- un terminal moderne — **Windows Terminal** recommandé (truecolor + Braille) ;
- [uv](https://docs.astral.sh/uv/) (gère Python 3.12 et les dépendances) ;
- un micro (sinon : `F2` déclenche l'écoute au clavier, ou `--demo` sans rien).

## Installation & premier lancement

```sh
uv sync
uv run halo
```

**GPU NVIDIA ?** Lance Halo avec l'extra CUDA — la reconnaissance vocale
devient quasi instantanée (~20× plus rapide que le CPU) :

```sh
uv run --extra cuda halo
```

⚠️ Garde le flag `--extra cuda` à **chaque** lancement : un `uv run halo` nu
re-synchronise l'environnement et retire les bibliothèques CUDA. L'app détecte
le matériel au premier lancement (NVIDIA / Apple Silicon / CPU) et te le dit à
l'accueil. Le réglage *Accélération STT* (Réglages ▸ Voix) est sur `auto` : GPU
si disponible, repli CPU silencieux sinon. `scripts/stt_check.py` (lance-le
aussi avec `--extra cuda`) affiche le device réellement utilisé.

Au premier lancement, Halo choisit automatiquement un vrai micro physique
(en évitant les périphériques virtuels type Voicemeeter), puis l'écran d'accueil
propose :
- **k** — saisir la clé d'API Anthropic → stockée dans le **trousseau de l'OS**
  (Credential Manager / Keychain), jamais dans un fichier ;
- **d** — télécharger le modèle vocal local (une seule fois ; `small` ≈ 250 Mo,
  `medium` ≈ 1,5 Go) ;
- **c** — **calibrer le micro** : un assistant guidé mesure le bruit ambiant puis
  ta voix, et règle automatiquement sensibilité, gain et seuil de détection à ta
  configuration. Re-jouable depuis Réglages ▸ Voix ▸ Calibrer le micro ;
- **Entrée** — entrer dans le tableau de bord.

## Usage

| Geste | Effet |
|---|---|
| « Claude, aide-moi » | terminal au premier plan, orbe centrée, écoute |
| *(3 s de silence)* | l'orbe se gare à gauche, le panneau se déploie, Claude répond |
| « Claude, … » (en session) | question suivante dans le même fil |
| `F2` | activation manuelle (sans le mot-clé) |
| `↑ ↓` | naviguer / faire défiler le fil |
| `tab` | sélectionner les boutons *Back to home* / *New session* |
| `Échap` | annuler l'écoute · revenir à l'accueil |

### Modes de démonstration

```sh
uv run halo --demo       # parcours complet scripté, sans micro ni clé API
uv run halo --orb-demo   # mise au point de l'orbe (espace · ↑↓ · m · échap)
```

## Utiliser ton abonnement Claude Pro/Max (sans crédits API)

L'abonnement Claude Pro ne couvre pas l'API, **mais il couvre Claude Code** —
et Halo sait passer par lui : **Réglages ▸ Claude/IA ▸ Source des réponses →
« Claude Code · abonnement Pro/Max »**. Les réponses transitent alors par ta
session `claude` déjà connectée (la CLI doit être installée et loguée), avec
~1-2 s de latence en plus par question. « Tester la connexion » vérifie que la
CLI est joignable. Bascule à chaud, l'API reste disponible en un cran de flèche.

## Configuration

Tout se règle dans le tableau de bord (sections **Claude/IA**, **Voix**,
**Apparence**, **Système**) et se persiste en TOML :
`%APPDATA%\claude-halo\config.toml` (Windows) / `~/Library/Application Support/claude-halo/` (macOS).
La clé d'API n'y figure jamais.

Variables d'environnement honorées : `NO_COLOR`, `HALO_REDUCED_MOTION=1`,
`HALO_THEME=dark|light`, `HALO_NO_BRAILLE=1`.

## Confidentialité

- Wake word **et** transcription 100 % locaux (faster-whisper) — aucun audio ne
  quitte la machine, rien n'est écrit sur disque ;
- seule la **question transcrite** part vers l'API Anthropic ;
- historique des échanges **désactivé par défaut** (opt-in, JSONL local,
  effaçable d'un geste) ; aucune télémétrie.

## Dépannage

- **« Requête refusée » alors que la clé est bonne** : ce sont souvent des
  **crédits épuisés** — le « Tester la connexion » le dit explicitement
  (console.anthropic.com ▸ Billing).
- **La transcription approxime tes mots** : avant tout, vérifie le **micro**.
  Lance `uv run python scripts/stt_check.py --list` : si ton micro par défaut
  est un périphérique **virtuel** (Voicemeeter, VB-Audio, CABLE, mixage), le son
  y est remixé/traité → STT dégradée. Choisis ton **micro physique** dans
  Réglages ▸ Voix ▸ Micro (les virtuels y sont signalés « · virtuel ⚠ » et
  classés en dernier). Compare ensuite les modèles sur ta voix :
  `uv run python scripts/stt_check.py --device <n> --models small,medium`.
  Ajoute ton jargon dans *Vocabulaire technique*, et sur GPU passe *Modèle STT*
  à `medium` (gratuit en latence) — le wake reste sur `small` pour la réactivité.
- **« C'est lent »** : le délai dominant est *Silence fin de question* (3 s par
  défaut) — descends-le à 1,5-2 s. La transcription, elle, démarre en avance
  (brouillon spéculatif dès ~1 s de silence) : à la fin du délai, le texte est
  déjà prêt.
- **Le micro ne capte rien (Windows)** : Paramètres → Confidentialité →
  Microphone → autoriser les applications de bureau.
- **La fenêtre ne passe pas devant** : Système → *Premier plan* (`toujours` /
  `seulement si non focus`) ; sous Windows Terminal le contournement ALT est
  appliqué automatiquement.
- **macOS** : l'autorisation micro est demandée au premier accès ; les adapters
  (premier plan, LaunchAgent) sont best-effort et non testés.
- **L'orbe s'affiche en points simples** : police sans Braille → change de police
  ou pose `HALO_NO_BRAILLE=1` pour assumer le repli.

## Architecture (pour les curieux)

Hexagonale : le **core** (`halo/core`) est pur — machine à états, session,
**contrat d'événements versionné** (`EVENTS_VERSION`) — testé sans micro, sans
réseau, sans écran. Tout le monde extérieur vit derrière des **ports**
(`audio/ports.py`, `ai/ports.py`, `platform/ports.py`) avec des adapters
interchangeables (réels, factices pour `--demo`). Le câblage se fait en un seul
endroit : `halo/app.py`. Cette couture rend le portage progressif (ex. moteur
audio en Rust, sidecar stdin/stdout) possible sans refonte.

```sh
uv run pytest -q      # 95 tests (core, audio, ui, ai, config, platform)
uv run ruff check .
uv run mypy           # strict sur halo/core
```
