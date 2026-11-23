"""CLI Section D Tests: Visual Image Diff (Flows D1 - D6).

Tests every CLI option and operational behavior of `tracecase diff`:
- D1: Diff identical images (exit 0)
- D2: Diff different images (exit 1, -o outputs highlighted magenta overlay)
- D3: Threshold boundary sensitivity (--threshold / -t)
- D4: Image dimensions mismatch handling & warning check (BUG-004)
- D5: Corrupt or unreadable image file (exit 2)
- D6: Diff execution without -o (stdout table only)
"""

from __future__ import annotations

from pathlib import Path
from PIL import Image
import pytest

from tests.dogfood.cli_tests.conftest import run_tracecase


def _create_sample_image(path: Path, color: tuple[int, int, int] = (255, 255, 255), size: tuple[int, int] = (100, 100)) -> Path:
    img = Image.new("RGB", size, color)
    img.save(path, format="PNG")
    return path


@pytest.mark.flow("D1")
def test_d1_diff_identical_images(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """D1: Diff identical images returns exit code 0."""
    img1 = _create_sample_image(isolated_workspace / "base.png", (200, 200, 200))
    img2 = _create_sample_image(isolated_workspace / "cand.png", (200, 200, 200))
    res = run_tracecase(["diff", str(img1), str(img2)], env=isolated_env)
    assert res.returncode == 0
    assert "Passed" in res.stdout
    assert "0.00%" in res.stdout


@pytest.mark.flow("D2")
def test_d2_diff_different_images_overlay(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """D2: Diff different images returns exit code 1 and writes magenta overlay to -o."""
    img1 = _create_sample_image(isolated_workspace / "base.png", (0, 0, 0))
    img2 = _create_sample_image(isolated_workspace / "cand.png", (255, 255, 255))
    diff_out = isolated_workspace / "diff.png"
    res = run_tracecase(["diff", str(img1), str(img2), "-o", str(diff_out)], env=isolated_env)
    assert res.returncode == 1
    assert "Failed" in res.stdout
    assert diff_out.exists(), f"Diff overlay {diff_out} was not generated"
    assert len(diff_out.read_bytes()) > 50


@pytest.mark.flow("D3")
def test_d3_threshold_boundary(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """D3: Threshold boundary: tolerance percentage dictates pass/fail."""
    img1 = Image.new("RGB", (100, 100), (0, 0, 0))
    img2 = Image.new("RGB", (100, 100), (0, 0, 0))
    for i in range(10):
        img2.putpixel((i, 0), (255, 255, 255))

    p1 = isolated_workspace / "t1.png"
    p2 = isolated_workspace / "t2.png"
    img1.save(p1)
    img2.save(p2)

    # 0.05% threshold fails
    res_fail = run_tracecase(["diff", str(p1), str(p2), "--threshold", "0.05"], env=isolated_env)
    assert res_fail.returncode == 1
    assert "Failed" in res_fail.stdout

    # 0.5% threshold passes
    res_pass = run_tracecase(["diff", str(p1), str(p2), "--threshold", "0.5"], env=isolated_env)
    assert res_pass.returncode == 0
    assert "Passed" in res_pass.stdout


@pytest.mark.flow("D4")
def test_d4_dimension_mismatch(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """D4: Image dimensions mismatch is padded gracefully, counted as diff, and exits 1."""
    img1 = _create_sample_image(isolated_workspace / "w100.png", size=(100, 100))
    img2 = _create_sample_image(isolated_workspace / "w200.png", size=(200, 100))
    res = run_tracecase(["diff", str(img1), str(img2)], env=isolated_env)
    assert res.returncode == 1
    assert "Diff Percentage" in res.stdout


@pytest.mark.flow("D4")
@pytest.mark.xfail(strict=True, reason="APP BUG-004: Dimension mismatch is hidden inside diff percentage without explicit warning")
def test_d4_dimension_mismatch_warning_reported(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """D4 (Audit): Verify whether image dimension mismatch is explicitly communicated in CLI output."""
    img1 = _create_sample_image(isolated_workspace / "w100.png", size=(100, 100))
    img2 = _create_sample_image(isolated_workspace / "w200.png", size=(200, 100))
    res = run_tracecase(["diff", str(img1), str(img2)], env=isolated_env)
    # The user expects an explicit dimension mismatch notice so human reviewers know images were different sizes
    assert "dimension mismatch" in res.stdout.lower() or "dimensions differ" in res.stdout.lower()


@pytest.mark.flow("D5")
def test_d5_corrupt_file(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """D5: Non-existent or corrupt image file triggers exit code 2."""
    good_img = _create_sample_image(isolated_workspace / "good.png")
    corrupt_file = isolated_workspace / "corrupt.png"
    corrupt_file.write_text("not an image binary", encoding="utf-8")

    res_missing = run_tracecase(["diff", str(isolated_workspace / "missing.png"), str(good_img)], env=isolated_env)
    assert res_missing.returncode == 2
    assert "not found" in (res_missing.stdout + res_missing.stderr).lower() or "error" in (res_missing.stdout + res_missing.stderr).lower()

    res_corrupt = run_tracecase(["diff", str(good_img), str(corrupt_file)], env=isolated_env)
    assert res_corrupt.returncode == 2
    assert "error" in (res_corrupt.stdout + res_corrupt.stderr).lower() or "cannot identify" in (res_corrupt.stdout + res_corrupt.stderr).lower()


@pytest.mark.flow("D6")
def test_d6_diff_without_output_flag(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """D6: Running diff without -o prints table and does not write diff image."""
    img1 = _create_sample_image(isolated_workspace / "base.png", (0, 0, 0))
    img2 = _create_sample_image(isolated_workspace / "cand.png", (255, 255, 255))
    res = run_tracecase(["diff", str(img1), str(img2)], env=isolated_env)
    assert res.returncode == 1
    assert "Visual Difference Report" in res.stdout
    assert "Diff Percentage" in res.stdout
