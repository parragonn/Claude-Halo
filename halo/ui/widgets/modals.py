"""Boîte modale d'édition : texte court, secret masqué ou texte long."""

from __future__ import annotations

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static, TextArea


class EditModal(ModalScreen[str | None]):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Annuler", show=False),
        Binding("ctrl+s", "save", "Enregistrer", show=False),
    ]

    DEFAULT_CSS = """
    EditModal { align: center middle; }
    EditModal > #dialog {
        width: 64;
        max-width: 90%;
        height: auto;
        padding: 1 2;
        border: round $halo-border;
    }
    EditModal #title { color: $halo-accent; text-style: bold; }
    EditModal #field { margin: 1 0 0 0; }
    EditModal #hint { color: $halo-dim; margin: 1 0 0 0; }
    EditModal Input { border: round $halo-border; }
    EditModal Input:focus { border: round $halo-dim; }
    EditModal TextArea { height: 9; border: round $halo-border; }
    EditModal TextArea:focus { border: round $halo-dim; }
    """

    def __init__(
        self,
        *,
        title: str,
        value: str = "",
        mask: bool = False,
        multiline: bool = False,
        placeholder: str = "",
    ) -> None:
        super().__init__()
        self._title = title
        self._value = value
        self._mask = mask
        self._multiline = multiline
        self._placeholder = placeholder

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self._title, id="title")
            if self._multiline:
                yield TextArea(self._value, id="field")
                hint = "ctrl+s valider · échap annuler"
            else:
                yield Input(
                    value=self._value,
                    password=self._mask,
                    placeholder=self._placeholder,
                    id="field",
                )
                hint = "entrée valider · échap annuler"
            yield Static(hint, id="hint")

    def on_mount(self) -> None:
        self.query_one("#field").focus()

    @on(Input.Submitted)
    def _submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_save(self) -> None:
        field = self.query_one("#field")
        value = field.text if isinstance(field, TextArea) else field.value  # type: ignore[attr-defined]
        self.dismiss(value)

    def action_cancel(self) -> None:
        self.dismiss(None)
