"""Sonde du backend Claude Code : pose une mini-question via l'abonnement.

Usage : uv run python scripts/probe_claude_code.py [modèle]
Vérifie de bout en bout : résolution de la CLI, flux stream-json, partiels,
session, complétion. Coût : un tout petit message d'abonnement.
"""

from __future__ import annotations

import asyncio
import sys

from halo.ai.claude_code_provider import ClaudeCodeProvider, resolve_claude_command
from halo.ai.ports import PromptRequest
from halo.core import events as ev


async def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    model = sys.argv[1] if len(sys.argv) > 1 else "claude-sonnet-4-6"
    print(f"CLI      : {resolve_claude_command()}")
    print(f"Modèle   : {model}")
    provider = ClaudeCodeProvider()
    request = PromptRequest(
        messages=({"role": "user", "content": "Réponds exactement : pong"},),
        model=model,
        effort="off",
        system_prompt="",
        language="fr",
        max_tokens=64,
    )
    chunks: list[str] = []

    def emit(event: ev.Event) -> None:
        match event:
            case ev.ResponseDelta(text=text):
                chunks.append(text)
                print("·", end="", flush=True)
            case ev.ResponseCompleted(input_tokens=i, output_tokens=o):
                print(f"\nOK : {''.join(chunks)!r}  (in={i}, out={o})")
            case ev.ResponseFailed(kind=kind, hint=hint):
                print(f"\nÉCHEC {kind.name} : {hint}")
            case _:
                pass

    await provider.respond(request, emit)


if __name__ == "__main__":
    asyncio.run(main())
