"""Panneau de réglages : sections bordées + navigation 100 % clavier.

Flèches ↑↓ pour naviguer, ◂ ▸ pour modifier, Entrée pour ouvrir/lancer.
Aucune souris requise (spec §5 IDLE/CONFIG).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll

from halo.ui.widgets.modals import EditModal
from halo.ui.widgets.rows import ActionRow, EditRow, Row, RowWidget


@dataclass
class Section:
    title: str
    rows: list[Row]


class SectionBox(Vertical):
    DEFAULT_CSS = """
    SectionBox {
        height: auto;
        border: round $halo-border;
        border-title-color: $halo-secondary;
        border-title-style: bold;
        padding: 1 2;
        margin: 0 0 1 0;
    }
    .compact SectionBox { padding: 0 2; margin: 0; }
    """

    def __init__(self, section: Section) -> None:
        super().__init__()
        self.border_title = section.title


class ConfigPanel(VerticalScroll):
    can_focus = True

    DEFAULT_CSS = """
    ConfigPanel {
        height: 1fr;
        padding: 0 1;
        scrollbar-size-vertical: 1;
    }
    """

    def __init__(self, sections: list[Section], on_change: Callable[[], None]) -> None:
        super().__init__()
        self._sections = sections
        self._on_change = on_change
        self._widgets: list[RowWidget] = []
        self._index = 0

    def compose(self) -> ComposeResult:
        self._widgets.clear()
        for section in self._sections:
            with SectionBox(section):
                for row in section.rows:
                    widget = RowWidget(row)
                    self._widgets.append(widget)
                    yield widget

    def on_mount(self) -> None:
        if self._widgets:
            self._widgets[self._index].selected = True

    @property
    def current_row(self) -> Row | None:
        return self._widgets[self._index].row if self._widgets else None

    def _select(self, index: int) -> None:
        if not self._widgets:
            return
        index = max(0, min(len(self._widgets) - 1, index))
        self._widgets[self._index].selected = False
        self._index = index
        widget = self._widgets[index]
        widget.selected = True
        widget.scroll_visible(animate=False)

    def _changed(self) -> None:
        self._on_change()
        if self._widgets:
            self._widgets[self._index].refresh()

    def _adjust(self, delta: int) -> None:
        row = self.current_row
        if row is not None and row.adjust(delta):
            self._changed()

    def _activate(self) -> None:
        row = self.current_row
        if isinstance(row, ActionRow):
            row.run()
        elif isinstance(row, EditRow):
            self._open_editor(row)
        elif row is not None:
            self._adjust(+1)

    def _open_editor(self, row: EditRow) -> None:
        modal = EditModal(
            title=row.prompt,
            value=row.get_text(),
            mask=row.mask,
            multiline=row.multiline,
            placeholder=row.placeholder,
        )

        def done(value: str | None) -> None:
            if value is not None:
                row.set_text(value)
                self._changed()

        self.app.push_screen(modal, done)

    def on_key(self, event: events.Key) -> None:
        key = event.key
        if key == "down":
            self._select(self._index + 1)
        elif key == "up":
            self._select(self._index - 1)
        elif key == "home":
            self._select(0)
        elif key == "end":
            self._select(len(self._widgets) - 1)
        elif key == "left":
            self._adjust(-1)
        elif key == "right":
            self._adjust(+1)
        elif key == "enter":
            self._activate()
        else:
            return
        event.stop()
        event.prevent_default()
