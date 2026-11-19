"""Tests for image comparison and visual diff metrics."""

from pathlib import Path

import pytest
from PIL import Image

from tracecase.replay.visual import VisualDiffResult, compare_images


def _create_image(
    path: Path, color: tuple[int, int, int], size: tuple[int, int] = (100, 100)
) -> Path:
    img = Image.new("RGB", size, color)
    img.save(path, format="PNG")
    return path


def test_identical_images_pass(temp_dir: Path) -> None:
    img1 = _create_image(temp_dir / "base.png", (255, 0, 0))
    img2 = _create_image(temp_dir / "cand.png", (255, 0, 0))

    res = compare_images(img1, img2)
    assert isinstance(res, VisualDiffResult)
    assert res.total_pixels == 10000
    assert res.diff_pixels == 0
    assert res.diff_percentage == 0.0
    assert res.passed is True
    assert res.diff_path is None


def test_modified_image_fails_and_generates_diff(temp_dir: Path) -> None:
    img1 = _create_image(temp_dir / "base.png", (255, 255, 255))

    # Create candidate with a black square in the middle
    cand = Image.new("RGB", (100, 100), (255, 255, 255))
    for x in range(40, 60):
        for y in range(40, 60):
            cand.putpixel((x, y), (0, 0, 0))
    cand_path = temp_dir / "cand.png"
    cand.save(cand_path, format="PNG")

    diff_out = temp_dir / "diff.png"
    res = compare_images(img1, cand_path, diff_output=diff_out, threshold_percent=0.1)

    assert res.total_pixels == 10000
    assert res.diff_pixels == 400
    assert res.diff_percentage == 4.0
    assert res.passed is False
    assert res.diff_path == str(diff_out)
    assert diff_out.exists()


def test_custom_threshold_passes(temp_dir: Path) -> None:
    img1 = _create_image(temp_dir / "base.png", (255, 255, 255))

    cand = Image.new("RGB", (100, 100), (255, 255, 255))
    # Modify 5 pixels (0.05%)
    for i in range(5):
        cand.putpixel((i, 0), (0, 0, 0))
    cand_path = temp_dir / "cand.png"
    cand.save(cand_path, format="PNG")

    # Default threshold 0.1% -> 0.05% should pass
    res = compare_images(img1, cand_path, threshold_percent=0.1)
    assert res.diff_pixels == 5
    assert res.diff_percentage == 0.05
    assert res.passed is True


def test_different_dimensions_handled(temp_dir: Path) -> None:
    img1 = _create_image(temp_dir / "base.png", (200, 200, 200), size=(100, 100))
    img2 = _create_image(temp_dir / "cand.png", (200, 200, 200), size=(100, 120))

    diff_out = temp_dir / "diff_dim.png"
    res = compare_images(img1, img2, diff_output=diff_out)
    # Total pixels is width * height of composite canvas: 100 * 120 = 12000
    assert res.total_pixels == 12000
    # The 20 extra lines (100 * 20 = 2000 pixels) differ from padding/missing base
    assert res.diff_pixels == 2000
    assert res.passed is False
    assert diff_out.exists()


def test_missing_file_raises_error(temp_dir: Path) -> None:
    img1 = _create_image(temp_dir / "base.png", (255, 0, 0))
    with pytest.raises(FileNotFoundError):
        compare_images(img1, temp_dir / "nonexistent.png")
