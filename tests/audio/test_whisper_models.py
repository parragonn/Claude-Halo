"""Répartition des modèles Whisper entre chemins chauds et finale."""

from __future__ import annotations

from halo.audio.whisper_models import hot_size, required_sizes


def test_hot_size_never_exceeds_small() -> None:
    assert hot_size("tiny") == "tiny"
    assert hot_size("small") == "small"
    assert hot_size("medium") == "small"


def test_required_sizes_cover_hot_and_final() -> None:
    assert required_sizes("small") == {"small"}
    assert required_sizes("medium") == {"small", "medium"}
    assert required_sizes("tiny") == {"tiny"}


def test_resolve_device_mapping() -> None:
    from halo.audio.stt import resolve_device

    # Bibliothèques CUDA présentes :
    assert resolve_device("cpu", cuda_failed=False, libs_present=True) == ("cpu", "int8")
    assert resolve_device("cuda", cuda_failed=False, libs_present=True) == ("cuda", "float16")
    assert resolve_device("auto", cuda_failed=False, libs_present=True) == ("cuda", "float16")
    # CUDA déjà constaté défaillant à l'usage → CPU :
    assert resolve_device("cuda", cuda_failed=True, libs_present=True) == ("cpu", "int8")
    # Bibliothèques CUDA absentes → CPU même si « cuda » est forcé (pas de crash) :
    assert resolve_device("cuda", cuda_failed=False, libs_present=False) == ("cpu", "int8")
    assert resolve_device("auto", cuda_failed=False, libs_present=False) == ("cpu", "int8")
