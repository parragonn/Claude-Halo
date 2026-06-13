"""Client Claude réel : streaming SDK Anthropic, erreurs → événements du domaine.

Mapping de l'« effort de réflexion » par modèle :
- modèles récents (Fable 5, Opus 4.x, Sonnet 4.6) : thinking adaptatif +
  `output_config.effort` ; « off » → on OMET le paramètre thinking (un
  `disabled` explicite est refusé par Fable 5) ;
- Haiku 4.5 (pas d'effort) : extended thinking à budget fixe, borné sous
  `max_tokens` (minimum API : 1024).
Aucun paramètre d'échantillonnage (temperature/top_p) : retirés des modèles
récents. Jamais de stack trace : toute erreur devient un ResponseFailed typé.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import anthropic

from halo.ai import catalog
from halo.ai.ports import ConnectionReport, PromptRequest
from halo.core import events as ev
from halo.core.models import FailureKind

_BASE_SYSTEM = (
    "Tu es Halo, un assistant vocal qui répond par écrit dans un terminal. "
    "La question a été dictée à l'oral et transcrite localement (Whisper) : "
    "tolère une ponctuation approximative. Réponds en Markdown sobre et lisible."
)

_LANGUAGE_HINT = {"fr": "Réponds en français.", "en": "Answer in English."}

_HAIKU_BUDGETS = {"low": 1024, "medium": 4096, "high": 8192}


def build_system_prompt(request: PromptRequest) -> str:
    parts = [_BASE_SYSTEM]
    hint = _LANGUAGE_HINT.get(request.language)
    if hint:
        parts.append(hint)
    if request.system_prompt:
        parts.append(request.system_prompt)
    return "\n\n".join(parts)


def thinking_params(request: PromptRequest) -> dict[str, Any]:
    """Paramètres thinking/effort adaptés au modèle choisi."""
    if request.effort == "off":
        return {}
    info = catalog.find(request.model)
    supports_effort = info.supports_effort if info is not None else True
    if supports_effort:
        return {
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": request.effort},
        }
    budget = min(_HAIKU_BUDGETS[request.effort], max(1024, request.max_tokens // 2))
    if budget >= request.max_tokens:
        return {}
    return {"thinking": {"type": "enabled", "budget_tokens": budget}}


class ClaudeClient:
    """Implémentation réelle du port ResponseProvider (streaming)."""

    def __init__(self, api_key_provider: Callable[[], str | None]) -> None:
        self._api_key_provider = api_key_provider

    async def respond(
        self, request: PromptRequest, emit: Callable[[ev.Event], None]
    ) -> None:
        api_key = self._api_key_provider()
        if not api_key:
            emit(ev.ResponseFailed(kind=FailureKind.AUTH, hint="aucune clé enregistrée"))
            return
        client = anthropic.AsyncAnthropic(api_key=api_key, timeout=90.0, max_retries=1)
        emit(ev.ResponseStarted())
        messages: list[Any] = list(request.messages)
        try:
            async with client.messages.stream(
                model=request.model,
                max_tokens=request.max_tokens,
                system=build_system_prompt(request),
                messages=messages,
                **thinking_params(request),
            ) as stream:
                async for text in stream.text_stream:
                    emit(ev.ResponseDelta(text=text))
                final = await stream.get_final_message()
            emit(
                ev.ResponseCompleted(
                    input_tokens=final.usage.input_tokens,
                    output_tokens=final.usage.output_tokens,
                )
            )
        except anthropic.AuthenticationError:
            emit(ev.ResponseFailed(kind=FailureKind.AUTH))
        except anthropic.PermissionDeniedError:
            emit(ev.ResponseFailed(kind=FailureKind.AUTH, hint="clé sans accès à ce modèle"))
        except anthropic.RateLimitError:
            emit(ev.ResponseFailed(kind=FailureKind.RATE_LIMIT))
        except anthropic.NotFoundError:
            emit(ev.ResponseFailed(kind=FailureKind.BAD_REQUEST, hint="modèle introuvable"))
        except anthropic.BadRequestError as exc:
            message = _api_message(exc)
            if _is_credit_issue(message):
                emit(ev.ResponseFailed(kind=FailureKind.BILLING))
            else:
                emit(ev.ResponseFailed(kind=FailureKind.BAD_REQUEST, hint=message))
        except anthropic.APITimeoutError:
            emit(ev.ResponseFailed(kind=FailureKind.TIMEOUT))
        except anthropic.APIConnectionError:
            emit(ev.ResponseFailed(kind=FailureKind.OFFLINE))
        except anthropic.APIStatusError as exc:
            kind = (
                FailureKind.OVERLOADED
                if exc.status_code in (500, 529)
                else FailureKind.UNKNOWN
            )
            emit(ev.ResponseFailed(kind=kind, hint=_brief(exc)))
        finally:
            await client.close()


def _brief(exc: Exception) -> str:
    message = getattr(exc, "message", None) or str(exc)
    return " ".join(str(message).split())[:160]


def _api_message(exc: Exception) -> str:
    """Le message propre de l'API (body.error.message) — jamais le JSON brut."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return " ".join(error["message"].split())[:200]
    return _brief(exc)


def _is_credit_issue(message: str) -> bool:
    return "credit balance" in message.lower()


async def check_connection(api_key: str, model: str) -> ConnectionReport:
    """Valide la clé + le modèle (count_tokens, gratuit) et rafraîchit la liste."""
    client = anthropic.AsyncAnthropic(api_key=api_key, timeout=20.0, max_retries=0)
    try:
        await client.messages.count_tokens(
            model=model, messages=[{"role": "user", "content": "ping"}]
        )
        models: list[catalog.ModelInfo] = []
        async for entry in client.models.list():
            model_id = getattr(entry, "id", "")
            if not model_id.startswith("claude-"):
                continue
            label = getattr(entry, "display_name", None) or model_id
            supports_effort = "haiku" not in model_id and not model_id.startswith("claude-3")
            models.append(catalog.ModelInfo(model_id, label, supports_effort))
            if len(models) >= 10:
                break
        return ConnectionReport(
            ok=True,
            message=f"connexion OK · {len(models)} modèles disponibles",
            models=tuple(models),
        )
    except anthropic.AuthenticationError:
        return ConnectionReport(False, "clé d'API invalide")
    except anthropic.NotFoundError:
        return ConnectionReport(False, "modèle introuvable avec cette clé")
    except anthropic.BadRequestError as exc:
        message = _api_message(exc)
        if _is_credit_issue(message):
            return ConnectionReport(
                False,
                "clé valide, mais crédits insuffisants — console.anthropic.com ▸ Billing",
            )
        return ConnectionReport(False, f"requête refusée : {message}")
    except anthropic.APIConnectionError:
        return ConnectionReport(False, "connexion impossible — vérifie le réseau")
    except anthropic.APIStatusError as exc:
        return ConnectionReport(False, f"API en erreur ({exc.status_code})")
    finally:
        await client.close()
