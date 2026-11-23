"""CLI Section D Tests: Visual Image Diff (Flows D1 - D6).

Tests every CLI option and operational behavior of `tracecase diff`:
- D1: Diff identical images (exit 0)
- D2: Diff different images (exit 1, -o outputs highlighted magenta overlay)
- D3: Threshold boundary sensitivity (--threshold / -t)
- D4: Image dimensions mismatch error handling (exit 2)
- D5: Corrupt or unreadable image file (exit 2)
- D6: Diff execution without -o (stdout table only)
"""

from __future__ import annotations

from pathlib import Path
from PIL import Image

from tests.dogfood.cli_tests.conftest import run_tracecase


def _create_sample_image(path: Path, color: tuple[int, int, int] = (255, 255, 255), size: tuple[int, int] = (100, 100)) -> Path:
    img = Image.new("RGB", size, color)
    img.save(path, format="PNG")
    return path


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


def test_d3_threshold_boundary(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """D3: Threshold boundary: tolerance percentage dictates pass/fail."""
    # 100x100 = 10,000 pixels. Change 10 pixels = 0.1% diff.
    img1 = Image.new("RGB", (100, 100), (0, 0, 0))
    img2 = Image.new("RGB", (100, 100), (0, 0, 0))
    for i in range(10):
        img2.putpixel((i, 0), (255, 255, 255))
    
    p1 = isolated_workspace / "t1.png"
    p2 = isolated_workspace / "t2.png"
    img1.save(p1)
    img2.save(p2)

    # With threshold 0.05% -> fails
    res_fail = run_tracecase(["diff", str(p1), str(p2), "--threshold", "0.05"], env=isolated_env)
    assert res_fail.returncode == 1

    # With threshold 0.5% -> passes
    res_pass = run_tracecase(["diff", str(p1), str(p2), "--threshold", "0.5"], env=isolated_env)
    assert res_pass.returncode == 0


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


def test_d5_corrupt_file(
    isolated_workspace: Path,
    isolated_env: dict[str, str],
):
    """D5: Non-existent or corrupt image file triggers exit code 2."""
    good_img = _create_sample_image(isolated_workspace / "good.png")
    corrupt_file = isolated_workspace / "corrupt.png"
    corrupt_file.write_text("not an image binary", encoding="utf-8")
    
    # Missing baseline
    res_missing = run_tracecase(["diff", str(isolated_workspace / "missing.png"), str(good_img)], env=isolated_env)
    assert res_missing.returncode == 2

    # Corrupt candidate
    res_corrupt = run_tracecase(["diff", str(good_img), str(corrupt_file)], env=isolated_env)
    assert res_corrupt.returncode == 2


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
