"""Commutateur de backend : délègue au provider choisi dans les réglages, à chaud."""

from __future__ import annotations

from collections.abc import Callable

from halo.ai.ports import PromptRequest, ResponseProvider
from halo.config.settings import Settings
from halo.core import events as ev


class SwitchableProvider:
    def __init__(
        self, settings: Settings, providers: dict[str, ResponseProvider], default: str = "api"
    ) -> None:
        self._settings = settings
        self._providers = providers
        self._default = default

    async def respond(
        self, request: PromptRequest, emit: Callable[[ev.Event], None]
    ) -> None:
        provider = self._providers.get(
            self._settings.ai.backend, self._providers[self._default]
        )
        await provider.respond(request, emit)
