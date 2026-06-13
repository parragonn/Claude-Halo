"""Lignes de réglage du tableau de bord : modèles de données + rendu.

Une ligne = un libellé à gauche, une valeur à droite. La hiérarchie passe par
le poids (gras/dim), jamais par des aplats : seule la ligne sélectionnée
reçoit l'accent (marqueur ▸ + valeur).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from halo.ui.app_link import halo_app


@dataclass
class ChoiceRow:
    label: str
    options: Sequence[tuple[str, str]]
    get: Callable[[], str]
    set: Callable[[str], None]

    def display(self) -> str:
        current = self.get()
        return next((text for value, text in self.options if value == current), current)

    def adjust(self, delta: int) -> bool:
        values = [value for value, _ in self.options]
        current = self.get()
        index = values.index(current) if current in values else 0
        self.set(values[(index + delta) % len(values)])
        return True


@dataclass
class NumericRow:
    label: str
    get: Callable[[], float]
    set: Callable[[float], None]
    minimum: float
    maximum: float
    step: float
    fmt: Callable[[float], str]

    def display(self) -> str:
        return self.fmt(self.get())

    def adjust(self, delta: int) -> bool:
        value = max(self.minimum, min(self.maximum, self.get() + delta * self.step))
        if value == self.get():
            return False
        self.set(value)
        return True


@dataclass
class ToggleRow:
    label: str
    get: Callable[[], bool]
    set: Callable[[bool], None]

    def display(self) -> str:
        return "● activé" if self.get() else "○ désactivé"

    def adjust(self, delta: int) -> bool:
        self.set(not self.get())
        return True


@dataclass
class ActionRow:
    label: str
    run: Callable[[], None]
    hint: str | Callable[[], str] = "lancer"

    def display(self) -> str:
        return self.hint() if callable(self.hint) else self.hint

    def adjust(self, delta: int) -> bool:
        return False


@dataclass
class EditRow:
    """Valeur éditée dans une boîte modale (texte libre ou secret masqué)."""

    label: str
    prompt: str
    display_value: Callable[[], str]
    get_text: Callable[[], str]
    set_text: Callable[[str], None]
    mask: bool = False
    multiline: bool = False
    placeholder: str = ""

    def display(self) -> str:
        return self.display_value()

    def adjust(self, delta: int) -> bool:
        return False


type Row = ChoiceRow | NumericRow | ToggleRow | ActionRow | EditRow

_ADJUSTABLE = (ChoiceRow, NumericRow, ToggleRow)


class RowWidget(Static):
    DEFAULT_CSS = """
    RowWidget { height: 1; }
    """

    selected = reactive(False)

    def __init__(self, row: Row) -> None:
        super().__init__()
        self.row = row

    def render(self) -> Text:
        palette = halo_app(self).palette
        text = Text(no_wrap=True, overflow="ellipsis")
        if self.selected:
            text.append("▸ ", style=f"bold {palette.accent}")
            text.append(f"{self.row.label:<26}", style="bold")
        else:
            text.append("  ")
            text.append(f"{self.row.label:<26}")
        value = self.row.display()
        if self.selected:
            if isinstance(self.row, _ADJUSTABLE):
                text.append("◂ ", style=palette.text_dim)
                text.append(value, style=f"bold {palette.accent}")
                text.append(" ▸", style=palette.text_dim)
            else:
                text.append(value, style=f"bold {palette.accent}")
                text.append("  ⏎", style=palette.text_dim)
        else:
            text.append(value, style=palette.text_secondary)
        return text
