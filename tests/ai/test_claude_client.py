"""Mapping effort/thinking par modèle et composition du system prompt."""

from __future__ import annotations

from typing import Any, ClassVar

from halo.ai import catalog
from halo.ai.claude_client import build_system_prompt, thinking_params
from halo.ai.ports import PromptRequest


def request(**overrides: Any) -> PromptRequest:
    base: dict[str, Any] = {
        "messages": ({"role": "user", "content": "salut"},),
        "model": "claude-opus-4-8",
        "effort": "medium",
        "system_prompt": "",
        "language": "fr",
        "max_tokens": 4096,
    }
    base.update(overrides)
    return PromptRequest(**base)


def test_effort_off_omits_thinking_entirely() -> None:
    # Un `disabled` explicite est refusé par Fable 5 : on omet le paramètre.
    assert thinking_params(request(effort="off", model="claude-fable-5")) == {}


def test_recent_models_use_adaptive_thinking_plus_effort() -> None:
    params = thinking_params(request(model="claude-opus-4-8", effort="high"))
    assert params["thinking"] == {"type": "adaptive"}
    assert params["output_config"] == {"effort": "high"}


def test_haiku_uses_bounded_budget_instead_of_effort() -> None:
    params = thinking_params(
        request(model="claude-haiku-4-5", effort="medium", max_tokens=4096)
    )
    assert params["thinking"]["type"] == "enabled"
    assert 1024 <= params["thinking"]["budget_tokens"] < 4096
    assert "output_config" not in params


def test_haiku_with_tiny_max_tokens_drops_thinking() -> None:
    # budget >= max_tokens serait un 400 : on préfère désactiver le thinking.
    assert thinking_params(request(model="claude-haiku-4-5", effort="low", max_tokens=1024)) == {}


def test_unknown_model_defaults_to_adaptive() -> None:
    params = thinking_params(request(model="claude-opus-9-9", effort="medium"))
    assert params["thinking"] == {"type": "adaptive"}


def test_system_prompt_composition_order() -> None:
    text = build_system_prompt(request(system_prompt="Parle comme un pirate.", language="fr"))
    assert "Halo" in text
    assert "français" in text
    assert text.index("Halo") < text.index("pirate")


def test_api_message_extracts_clean_body_message() -> None:
    from halo.ai.claude_client import _api_message, _is_credit_issue

    class FakeApiError(Exception):
        body: ClassVar[dict[str, Any]] = {
            "type": "error",
            "error": {
                "type": "invalid_request_error",
                "message": "Your credit balance is too low to access the Anthropic API.",
            },
        }

    message = _api_message(FakeApiError("Error code: 400 - {...json brut...}"))
    assert message.startswith("Your credit balance")
    assert "{" not in message
    assert _is_credit_issue(message)
    assert not _is_credit_issue("model not found")


def test_catalog_dynamic_update_then_reset() -> None:
    try:
        catalog.update_from_api((catalog.ModelInfo("claude-test-1", "Test 1"),))
        assert catalog.choices()[0][0] == "claude-test-1"
        assert catalog.find("claude-test-1") is not None
        assert catalog.find("claude-haiku-4-5") is not None  # les curatés restent trouvables
    finally:
        catalog.update_from_api(())
    assert catalog.choices()[0][0] == "claude-opus-4-8"
