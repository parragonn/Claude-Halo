"""Accès typé à l'app Halo depuis les widgets, sans import circulaire."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from textual.dom import DOMNode

    from halo.ui.tui_app import HaloApp


def halo_app(node: DOMNode) -> HaloApp:
    return cast("HaloApp", node.app)
