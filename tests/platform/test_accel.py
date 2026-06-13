"""Sonde d'accélération : classification déterministe par plateforme."""

from __future__ import annotations

from halo.platform.accel import probe_accelerator


def test_apple_silicon_is_cpu_accelerate() -> None:
    report = probe_accelerator(os_name="darwin", machine="arm64")
    assert report.kind == "apple"
    assert not report.cuda_ready
    assert "Accelerate" in report.label


def test_nvidia_with_libraries_is_cuda_ready() -> None:
    report = probe_accelerator(
        os_name="win32", machine="amd64", cuda_device_count=1, cudnn_installed=True
    )
    assert report.kind == "nvidia"
    assert report.cuda_ready
    assert report.hint == ""


def test_nvidia_without_libraries_suggests_the_extra() -> None:
    report = probe_accelerator(
        os_name="win32", machine="amd64", cuda_device_count=1, cudnn_installed=False
    )
    assert report.kind == "nvidia"
    assert not report.cuda_ready
    assert "--extra cuda" in report.hint


def test_no_gpu_is_plain_cpu() -> None:
    report = probe_accelerator(
        os_name="win32", machine="amd64", cuda_device_count=0, cudnn_installed=False
    )
    assert report.kind == "cpu"
    assert not report.cuda_ready
