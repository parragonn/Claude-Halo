"""Détection du mot-clé par correspondance floue sur la transcription locale.

Pur (zéro I/O) : normalisation sans accents, distance de Levenshtein bornée,
alignement ordonné des jetons de la phrase. En mode « suite de session »,
le premier jeton seul suffit (« Claude, … » enchaîne sans la phrase complète).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def normalize_words(text: str) -> list[str]:
    """Minuscules, sans accents ni ponctuation → liste de mots."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    cleaned = "".join(
        c if c.isalnum() else " " for c in decomposed if not unicodedata.combining(c)
    )
    return cleaned.split()


def levenshtein(a: str, b: str, limit: int) -> int:
    """Distance d'édition, court-circuitée au-delà de `limit`."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        best = i
        for j, char_b in enumerate(b, start=1):
            cost = 0 if char_a == char_b else 1
            value = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            current.append(value)
            best = min(best, value)
        if best > limit:
            return limit + 1
        previous = current
    return previous[-1]


def _tolerance(token: str) -> int:
    return 1 if len(token) <= 4 else 2


def strip_phrase_prefix(text: str, phrase: str) -> str:
    """Retire la phrase d'activation (ou sa fin) résiduelle en tête d'une
    transcription : la capture embarque la queue audio du wake, la finale
    commence donc souvent par « …aide-moi. ». Un seul mot isolé n'est jamais
    retiré (sauf phrase d'un seul mot), pour ne pas amputer une vraie question.
    """
    raw_tokens = [t for t in re.split(r"\W+", phrase) if t]
    if not raw_tokens:
        return text
    for start in range(len(raw_tokens)):
        tokens = raw_tokens[start:]
        if len(tokens) < 2 and tokens != raw_tokens[:1]:
            continue
        pattern = r"^\W*" + r"\W+".join(re.escape(t) for t in tokens) + r"[\s,.!?;:–—-]*"
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if match:
            return text[match.end() :].lstrip()
    return text


@dataclass(frozen=True, slots=True)
class WakeMatch:
    residual_text: str


class WakePhraseMatcher:
    def __init__(self, phrase: str) -> None:
        self.tokens = [t for t in normalize_words(phrase) if len(t) >= 2]
        if not self.tokens:
            self.tokens = ["claude"]

    def match(self, transcript: str, *, require_all: bool = True) -> WakeMatch | None:
        words = normalize_words(transcript)
        tokens = self.tokens if require_all else self.tokens[:1]
        for start in range(len(words)):
            end = self._align(words, start, tokens)
            if end is not None:
                return WakeMatch(residual_text=" ".join(words[end:]))
        return None

    def _align(self, words: list[str], start: int, tokens: list[str]) -> int | None:
        """Aligne les jetons en ordre depuis `start` (1 mot d'écart toléré)."""
        position = start
        for token in tokens:
            found = None
            for offset in range(2):  # le mot attendu, ou le suivant
                index = position + offset
                if index >= len(words):
                    break
                if levenshtein(words[index], token, _tolerance(token)) <= _tolerance(token):
                    found = index
                    break
            if found is None:
                return None
            position = found + 1
        return position
