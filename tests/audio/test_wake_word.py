"""Correspondance floue du mot-clé : normalisation, distance, alignement."""

from __future__ import annotations

from halo.audio.wake_word import WakePhraseMatcher, levenshtein, normalize_words


def matcher() -> WakePhraseMatcher:
    return WakePhraseMatcher("Claude, aide-moi")


def test_normalize_strips_accents_and_punctuation() -> None:
    assert normalize_words("Claude, aide-moi !") == ["claude", "aide", "moi"]
    assert normalize_words("Déjà vu… évidemment") == ["deja", "vu", "evidemment"]


def test_levenshtein_basics() -> None:
    assert levenshtein("claude", "claude", 2) == 0
    assert levenshtein("claude", "cloud", 2) == 2
    assert levenshtein("abc", "xyz", 1) == 2  # court-circuit au-delà de la limite


def test_full_phrase_matches_and_keeps_residual() -> None:
    result = matcher().match("ok claude aide moi quelle heure est il")
    assert result is not None
    assert result.residual_text == "quelle heure est il"


def test_fuzzy_variants_of_claude() -> None:
    assert matcher().match("clode aide moi") is not None
    assert matcher().match("cloud aide moi bonjour") is not None


def test_one_filler_word_is_tolerated() -> None:
    assert matcher().match("claude euh aide moi") is not None


def test_rejects_unrelated_speech() -> None:
    assert matcher().match("bonjour tout le monde il fait beau") is None


def test_idle_mode_requires_the_full_phrase() -> None:
    assert matcher().match("claude quelle heure est il") is None


def test_followup_mode_needs_only_the_name() -> None:
    result = matcher().match("claude quelle heure est il", require_all=False)
    assert result is not None
    assert result.residual_text == "quelle heure est il"


def test_strip_phrase_prefix_removes_full_phrase() -> None:
    from halo.audio.wake_word import strip_phrase_prefix

    cleaned = strip_phrase_prefix(
        "Claude, aide-moi. Comment apprendre Rust et TypeScript ?", "Claude, aide-moi"
    )
    assert cleaned == "Comment apprendre Rust et TypeScript ?"


def test_strip_phrase_prefix_removes_trailing_fragment() -> None:
    from halo.audio.wake_word import strip_phrase_prefix

    assert (
        strip_phrase_prefix("aide-moi, quelle heure est-il ?", "Claude, aide-moi")
        == "quelle heure est-il ?"
    )


def test_strip_phrase_prefix_keeps_real_questions() -> None:
    from halo.audio.wake_word import strip_phrase_prefix

    assert strip_phrase_prefix("Comment vas-tu ?", "Claude, aide-moi") == "Comment vas-tu ?"
    # « moi » seul n'est jamais retiré : ce serait amputer une vraie question.
    assert strip_phrase_prefix("Moi je veux du café", "Claude, aide-moi") == (
        "Moi je veux du café"
    )


def test_strip_phrase_prefix_single_word_phrase() -> None:
    from halo.audio.wake_word import strip_phrase_prefix

    assert strip_phrase_prefix("Jarvis, montre la météo", "jarvis") == "montre la météo"


def test_strip_phrase_prefix_phrase_only_yields_empty() -> None:
    from halo.audio.wake_word import strip_phrase_prefix

    # L'utilisateur n'a dit que la phrase : question vide → l'app retourne au repos.
    assert strip_phrase_prefix("Claude, aide-moi.", "Claude, aide-moi") == ""


def test_custom_phrase() -> None:
    custom = WakePhraseMatcher("jarvis")
    result = custom.match("jarvis montre les actualités")
    assert result is not None
    assert result.residual_text == "montre les actualites"
