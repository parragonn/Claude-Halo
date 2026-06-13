"""Fil de conversation scrollable : tours séparés, révélation configurable,
scrollbar fantôme, auto-scroll respectueux de la lecture (spec §5 SESSION).
"""

from __future__ import annotations

from rich.text import Text
from textual.color import Color
from textual.containers import Vertical, VerticalScroll
from textual.timer import Timer
from textual.widgets import Markdown, Static

from halo.ui.animation import DUR_BASE, EASING
from halo.ui.app_link import halo_app

_TYPEWRITER_CHARS_PER_FLUSH = 14  # ~140 caractères/s à 10 Hz


class TurnView(Vertical):
    """Un tour : question en tête (dim), réponse Markdown en dessous."""

    DEFAULT_CSS = """
    TurnView { height: auto; margin: 0 0 1 0; }
    TurnView.-followup {
        border-top: solid $halo-border;
        padding: 1 0 0 0;
        margin: 1 0 1 0;
    }
    TurnView #q { height: auto; margin: 0 0 1 0; }
    """

    def __init__(
        self, question: str, *, reveal: str, animate_in: bool, followup: bool
    ) -> None:
        super().__init__(classes="-followup" if followup else "")
        self._question_text = question
        self._reveal = reveal  # fade | typewriter | instant
        self._animate_in = animate_in
        self._md = Markdown("")
        self._pending = ""
        self._shown = ""
        self._done = False

    def compose(self):  # type: ignore[no-untyped-def]
        yield Static("", id="q")
        yield self._md

    def on_mount(self) -> None:
        palette = halo_app(self).palette
        header = Text(no_wrap=False)
        header.append("❝ ", style=palette.accent_deep)
        header.append(self._question_text, style=palette.text_dim)
        header.append(" ❞", style=palette.accent_deep)
        self.query_one("#q", Static).update(header)
        if self._animate_in:
            self.styles.opacity = 0.0
            self.styles.animate("opacity", 1.0, duration=DUR_BASE, easing=EASING)

    # ── flux de réponse ──────────────────────────────────────────────────────

    def append(self, delta: str) -> None:
        self._pending += delta

    def finish(self) -> None:
        self._done = True

    def fail(self, message: str) -> None:
        self._pending = ""
        self._done = True
        self._shown = f"**Un souci :** {message}\n\n_Redis « Claude, … » pour réessayer._"
        self._md.update(self._shown)

    def flush(self) -> bool:
        """Déverse le texte en attente selon le mode ; True si l'affichage a changé."""
        if self._reveal == "instant" and not self._done:
            return False
        if not self._pending:
            return False
        if self._reveal == "typewriter" and not self._done:
            take = min(len(self._pending), _TYPEWRITER_CHARS_PER_FLUSH)
            chunk, self._pending = self._pending[:take], self._pending[take:]
            self._shown += chunk
        else:
            self._shown += self._pending
            self._pending = ""
        self._md.update(self._shown)
        return True


class NewReplyPill(Static):
    """« ▾ nouvelle réponse » — apparaît quand l'utilisateur lit plus haut."""

    DEFAULT_CSS = """
    NewReplyPill { height: 1; opacity: 0; margin: 0 2; }
    """

    def render(self) -> Text:
        palette = halo_app(self).palette
        text = Text(justify="right", no_wrap=True)
        text.append("▾ nouvelle réponse", style=palette.accent_soft)
        return text

    def show(self, animate: bool) -> None:
        if animate:
            self.styles.animate("opacity", 1.0, duration=DUR_BASE, easing=EASING)
        else:
            self.styles.opacity = 1.0

    def conceal(self, animate: bool) -> None:
        if animate:
            self.styles.animate("opacity", 0.0, duration=DUR_BASE, easing=EASING)
        else:
            self.styles.opacity = 0.0


class ThreadView(VerticalScroll):
    """Le fil : scroll libre aux flèches, ascenseur fantôme, auto-scroll poli."""

    DEFAULT_CSS = """
    ThreadView {
        height: 1fr;
        padding: 0 1;
        scrollbar-size-vertical: 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._hide_timer: Timer | None = None
        self._pill: NewReplyPill | None = None

    def attach_pill(self, pill: NewReplyPill) -> None:
        self._pill = pill

    def on_mount(self) -> None:
        self._set_scrollbar(visible=False, animate=False)
        self.watch(self, "scroll_y", self._on_scrolled, init=False)

    # ── contenu ──────────────────────────────────────────────────────────────

    @property
    def turn_count(self) -> int:
        return len(self.query(TurnView))

    def add_turn(self, turn: TurnView) -> None:
        self.mount(turn)
        self.scroll_end(animate=False)

    def content_grew(self) -> None:
        """Nouvelle matière en bas : suit si le lecteur y est déjà, sinon pastille."""
        if self.is_vertical_scroll_end:
            self.scroll_end(animate=False)
            if self._pill is not None:
                self._pill.conceal(animate=False)
        elif self._pill is not None:
            self._pill.show(halo_app(self).motion.enabled)

    def clear_turns(self) -> None:
        self.query(TurnView).remove()
        if self._pill is not None:
            self._pill.conceal(animate=False)

    # ── ascenseur fantôme ────────────────────────────────────────────────────

    def _on_scrolled(self) -> None:
        self._set_scrollbar(visible=True, animate=halo_app(self).motion.enabled)
        if self._hide_timer is not None:
            self._hide_timer.stop()
        self._hide_timer = self.set_timer(0.8, self._fade_out_scrollbar)
        if self.is_vertical_scroll_end and self._pill is not None:
            self._pill.conceal(halo_app(self).motion.enabled)

    def _fade_out_scrollbar(self) -> None:
        self._set_scrollbar(visible=False, animate=halo_app(self).motion.enabled)

    def _set_scrollbar(self, *, visible: bool, animate: bool) -> None:
        palette = halo_app(self).palette
        color = Color.parse(palette.border) if visible else Color(0, 0, 0, 0)
        active = Color.parse(palette.accent) if visible else Color(0, 0, 0, 0)
        try:
            if animate:
                self.styles.animate("scrollbar_color", color, duration=DUR_BASE)
            else:
                self.styles.scrollbar_color = color
            self.styles.scrollbar_color_hover = active
            self.styles.scrollbar_color_active = active
            self.styles.scrollbar_background = Color(0, 0, 0, 0)
        except Exception:
            self.styles.scrollbar_color = color  # repli : bascule instantanée
