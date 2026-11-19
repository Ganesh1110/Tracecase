"""Tests for visual diff CLI commands and options."""

from pathlib import Path

from PIL import Image
from typer.testing import CliRunner

from tracecase.cli import app

runner = CliRunner()


def _create_image(
    path: Path, color: tuple[int, int, int], size: tuple[int, int] = (100, 100)
) -> Path:
    img = Image.new("RGB", size, color)
    img.save(path, format="PNG")
    return path


def test_cli_diff_two_identical_images(temp_dir: Path) -> None:
    img1 = _create_image(temp_dir / "base.png", (255, 0, 0))
    img2 = _create_image(temp_dir / "cand.png", (255, 0, 0))

    result = runner.invoke(app, ["diff", str(img1), str(img2)])
    assert result.exit_code == 0
    assert "Passed" in result.stdout or "0.0%" in result.stdout


def test_cli_diff_two_different_images(temp_dir: Path) -> None:
    img1 = _create_image(temp_dir / "base.png", (255, 255, 255))
    img2 = _create_image(temp_dir / "cand.png", (0, 0, 0))
    diff_out = temp_dir / "diff.png"

    result = runner.invoke(app, ["diff", str(img1), str(img2), "-o", str(diff_out)])
    assert result.exit_code == 1
    assert "Failed" in result.stdout or "100.0%" in result.stdout
    assert diff_out.exists()


def test_cli_diff_missing_file_exits_2(temp_dir: Path) -> None:
    img1 = _create_image(temp_dir / "base.png", (255, 0, 0))
    result = runner.invoke(app, ["diff", str(img1), str(temp_dir / "nonexistent.png")])
    assert result.exit_code == 2
