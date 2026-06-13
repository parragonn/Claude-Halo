"""Réponses via Claude Code en mode headless — couvertes par l'abonnement Pro/Max.

`claude -p --output-format stream-json --include-partial-messages` streame des
lignes JSON ; on les interprète en événements du domaine. La question part par
stdin (aucun argument avec espaces → l'enrobage .cmd de npm sous Windows reste
sûr). Le fil de conversation s'appuie sur les sessions natives de Claude Code
(`--resume`). Tout échec devient un ResponseFailed propre, jamais une trace.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from halo.ai.ports import ConnectionReport, PromptRequest
from halo.core import events as ev
from halo.core.models import FailureKind

_LANGUAGE_HINT = {"fr": "Réponds en français.", "en": "Answer in English."}

_TIMEOUT_S = 180.0
_STREAM_LIMIT = 4 * 1024 * 1024  # certaines lignes JSON portent la réponse entière


# ── localisation de l'exécutable ─────────────────────────────────────────────


def resolve_claude_command() -> list[str] | None:
    """Commande de lancement de la CLI `claude`, exécutable sans shell.

    Sous Windows, l'install npm expose un wrapper .cmd : on préfère lancer
    directement `node cli.js` (quoting sûr), sinon on passe par `cmd /c`
    (sans risque : aucun de nos arguments ne contient d'espace).
    """
    for name in ("claude.exe", "claude"):
        found = shutil.which(name)
        if not found:
            continue
        lowered = found.lower()
        if lowered.endswith((".cmd", ".bat")):
            package = Path(found).parent / "node_modules" / "@anthropic-ai" / "claude-code"
            cli_js = package / "cli.js"
            node = shutil.which("node")
            if node and cli_js.exists():
                return [node, str(cli_js)]
            return ["cmd.exe", "/c", found]
        return [found]
    return None


# ── interprétation du flux stream-json (pur, testé) ──────────────────────────


@dataclass(frozen=True, slots=True)
class StreamItem:
    kind: str  # session | delta | full_text | done | error | noise
    text: str = ""
    session_id: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    error_hint: str = ""


def interpret_line(data: dict[str, Any]) -> StreamItem:
    kind = data.get("type")
    if kind == "system" and data.get("subtype") == "init":
        return StreamItem("session", session_id=str(data.get("session_id", "")))
    if kind == "stream_event":
        event = data.get("event") or {}
        if event.get("type") == "content_block_delta":
            delta = event.get("delta") or {}
            if delta.get("type") == "text_delta":
                return StreamItem("delta", text=str(delta.get("text", "")))
        return StreamItem("noise")
    if kind == "assistant":
        message = data.get("message") or {}
        parts = [
            str(block.get("text", ""))
            for block in message.get("content") or []
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return StreamItem("full_text", text="".join(parts))
    if kind == "result":
        session_id = str(data.get("session_id", ""))
        if data.get("subtype") == "success" and not data.get("is_error"):
            usage = data.get("usage") or {}
            return StreamItem(
                "done",
                session_id=session_id,
                input_tokens=int(usage.get("input_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or 0),
            )
        hint = str(data.get("result") or data.get("subtype") or "échec Claude Code")
        return StreamItem("error", error_hint=" ".join(hint.split())[:200])
    return StreamItem("noise")


def _failure_from_stderr(stderr: str) -> tuple[FailureKind, str]:
    lowered = stderr.lower()
    if "log in" in lowered or "login" in lowered or "authent" in lowered:
        return FailureKind.AUTH, "Claude Code n'est pas connecté — lance `claude` puis /login"
    if "model" in lowered:
        return FailureKind.BAD_REQUEST, "modèle non disponible via Claude Code — essaie Opus/Sonnet"
    return FailureKind.UNKNOWN, " ".join(stderr.split())[:160] or "Claude Code a échoué"


# ── le provider ───────────────────────────────────────────────────────────────


@dataclass
class _Outcome:
    completed: bool = False
    failed: bool = False
    saw_delta: bool = False
    full_text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    stderr: str = ""
    exit_code: int | None = None
    flag_unsupported: bool = False
    resume_invalid: bool = False
    error: tuple[FailureKind, str] = field(default=(FailureKind.UNKNOWN, ""))


class ClaudeCodeProvider:
    """Port ResponseProvider adossé à la session Claude Code de l'utilisateur."""

    def __init__(self) -> None:
        self._session_id: str | None = None
        self._partials_supported = True

    def _prompt(self, request: PromptRequest, resuming: bool) -> str:
        parts = [
            "Tu es Halo, un assistant vocal qui répond par écrit dans un terminal. "
            "La question a été dictée à l'oral (transcription locale, ponctuation "
            "approximative). Réponds directement en Markdown sobre, sans utiliser d'outils."
        ]
        hint = _LANGUAGE_HINT.get(request.language)
        if hint:
            parts.append(hint)
        if request.system_prompt:
            parts.append(request.system_prompt)
        if not resuming and len(request.messages) > 1:
            history = "\n".join(
                f"- {'Q' if m['role'] == 'user' else 'R'} : {m['content'][:300]}"
                for m in request.messages[:-1]
            )
            parts.append(f"Contexte des échanges précédents :\n{history}")
        question = request.messages[-1]["content"] if request.messages else ""
        parts.append(f"Question : {question}")
        return "\n\n".join(parts)

    async def respond(
        self, request: PromptRequest, emit: Callable[[ev.Event], None]
    ) -> None:
        command = resolve_claude_command()
        if command is None:
            emit(
                ev.ResponseFailed(
                    kind=FailureKind.BAD_REQUEST,
                    hint="CLI `claude` introuvable — installe Claude Code ou repasse sur l'API",
                )
            )
            return
        emit(ev.ResponseStarted())
        resume = self._session_id if len(request.messages) > 1 else None
        outcome = await self._run(command, request, emit, resume=resume)
        if outcome.resume_invalid and resume is not None:
            self._session_id = None
            outcome = await self._run(command, request, emit, resume=None)
        elif outcome.flag_unsupported and self._partials_supported:
            self._partials_supported = False
            outcome = await self._run(command, request, emit, resume=resume)

        if outcome.completed:
            if not outcome.saw_delta and outcome.full_text:
                emit(ev.ResponseDelta(text=outcome.full_text))
            emit(
                ev.ResponseCompleted(
                    input_tokens=outcome.input_tokens, output_tokens=outcome.output_tokens
                )
            )
        elif outcome.failed:
            kind, hint = outcome.error
            emit(ev.ResponseFailed(kind=kind, hint=hint))
        else:
            kind, hint = _failure_from_stderr(outcome.stderr)
            emit(ev.ResponseFailed(kind=kind, hint=hint))

    async def _run(
        self,
        command: list[str],
        request: PromptRequest,
        emit: Callable[[ev.Event], None],
        *,
        resume: str | None,
    ) -> _Outcome:
        outcome = _Outcome()
        args = ["-p", "--output-format", "stream-json", "--verbose", "--max-turns", "1"]
        if self._partials_supported:
            args += ["--include-partial-messages"]
        args += ["--model", request.model]
        if resume:
            args += ["--resume", resume]
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=_STREAM_LIMIT,
                cwd=str(Path.home()),
            )
        except OSError as exc:
            outcome.failed = True
            outcome.error = (FailureKind.UNKNOWN, f"lancement de Claude Code impossible ({exc})")
            return outcome

        assert process.stdin and process.stdout and process.stderr
        try:
            async with asyncio.timeout(_TIMEOUT_S):
                process.stdin.write(self._prompt(request, resuming=resume is not None).encode())
                await process.stdin.drain()
                process.stdin.close()
                stderr_task = asyncio.create_task(process.stderr.read())
                async for raw in process.stdout:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("{"):
                        continue
                    try:
                        item = interpret_line(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                    if item.kind == "session" and item.session_id:
                        self._session_id = item.session_id
                    elif item.kind == "delta" and item.text:
                        outcome.saw_delta = True
                        emit(ev.ResponseDelta(text=item.text))
                    elif item.kind == "full_text":
                        outcome.full_text = item.text
                    elif item.kind == "done":
                        outcome.completed = True
                        outcome.input_tokens = item.input_tokens
                        outcome.output_tokens = item.output_tokens
                        if item.session_id:
                            self._session_id = item.session_id
                    elif item.kind == "error":
                        outcome.failed = True
                        outcome.error = (FailureKind.UNKNOWN, item.error_hint)
                outcome.exit_code = await process.wait()
                outcome.stderr = (await stderr_task).decode("utf-8", "replace")
        except TimeoutError:
            process.kill()
            outcome.failed = True
            outcome.error = (FailureKind.TIMEOUT, "Claude Code n'a pas répondu à temps")
            return outcome
        except asyncio.CancelledError:
            process.kill()
            raise

        lowered = outcome.stderr.lower()
        if outcome.exit_code and "--include-partial-messages" in lowered:
            outcome.flag_unsupported = True
        if outcome.exit_code and resume and ("session" in lowered or "resume" in lowered):
            outcome.resume_invalid = True
        if outcome.exit_code and not outcome.completed and not outcome.failed:
            pass  # mappé via _failure_from_stderr par l'appelant
        return outcome


async def check_claude_code() -> ConnectionReport:
    """Vérifie que la CLI `claude` est joignable (l'auth se voit à la 1re question)."""
    command = resolve_claude_command()
    if command is None:
        return ConnectionReport(
            False, "CLI `claude` introuvable — installe Claude Code (npm i -g …) ou choisis l'API"
        )
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        async with asyncio.timeout(15):
            stdout, _stderr = await process.communicate()
        version = stdout.decode("utf-8", "replace").strip().splitlines()
        label = version[0] if version else "version inconnue"
        return ConnectionReport(
            True, f"Claude Code détecté ({label}) — réponses via ton abonnement"
        )
    except (OSError, TimeoutError):
        return ConnectionReport(False, "Claude Code ne répond pas — vérifie l'installation")
