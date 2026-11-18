"""Visual regression testing and pixel diff comparison using Pillow."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from PIL import Image
from pydantic import BaseModel, Field


class VisualDiffResult(BaseModel):
    """Result of comparing two screenshots."""

    baseline_path: str
    candidate_path: str
    diff_path: str | None = None
    total_pixels: int = Field(ge=0)
    diff_pixels: int = Field(ge=0)
    diff_percentage: float = Field(ge=0.0, le=100.0)
    passed: bool


def compare_images(
    baseline: Path | str,
    candidate: Path | str,
    diff_output: Path | str | None = None,
    threshold_percent: float = 0.1,
    color_tolerance: int = 16,
) -> VisualDiffResult:
    """Compare two images pixel-by-pixel, compute diff metrics, and optionally save a highlighted diff.

    Args:
        baseline: Path to the reference / baseline screenshot.
        candidate: Path to the current / replayed screenshot.
        diff_output: Optional path to save the generated diff PNG.
        threshold_percent: Maximum acceptable differing pixels percentage (default 0.1%).
        color_tolerance: Per-channel RGB color distance allowed before counting as a diff.

    Returns:
        VisualDiffResult containing metrics, pass/fail status, and diff path.
    """
    base_file = Path(baseline)
    cand_file = Path(candidate)

    if not base_file.exists():
        raise FileNotFoundError(f"Baseline image not found: {base_file}")
    if not cand_file.exists():
        raise FileNotFoundError(f"Candidate image not found: {cand_file}")

    with Image.open(base_file) as base_raw, Image.open(cand_file) as cand_raw:
        base_img = base_raw.convert("RGBA")
        cand_img = cand_raw.convert("RGBA")

    max_w = max(base_img.width, cand_img.width)
    max_h = max(base_img.height, cand_img.height)
    total_pixels = max_w * max_h

    # Normalize to matching canvas if dimensions differ
    if base_img.size != (max_w, max_h):
        padded_base = Image.new("RGBA", (max_w, max_h), (0, 0, 0, 0))
        padded_base.paste(base_img, (0, 0))
        base_img = padded_base

    if cand_img.size != (max_w, max_h):
        padded_cand = Image.new("RGBA", (max_w, max_h), (0, 0, 0, 0))
        padded_cand.paste(cand_img, (0, 0))
        cand_img = padded_cand

    base_pix = cast(Any, base_img.load())
    cand_pix = cast(Any, cand_img.load())

    diff_pixels = 0
    diff_mask: list[tuple[int, int]] = []

    for y in range(max_h):
        for x in range(max_w):
            r1, g1, b1, a1 = base_pix[x, y]
            r2, g2, b2, a2 = cand_pix[x, y]

            if (
                abs(r1 - r2) > color_tolerance
                or abs(g1 - g2) > color_tolerance
                or abs(b1 - b2) > color_tolerance
                or abs(a1 - a2) > color_tolerance
            ):
                diff_pixels += 1
                if diff_output:
                    diff_mask.append((x, y))

    diff_percentage = round((diff_pixels / total_pixels) * 100.0, 4) if total_pixels > 0 else 0.0
    passed = diff_percentage <= threshold_percent

    saved_diff_path: str | None = None
    if diff_output and diff_pixels > 0:
        out_path = Path(diff_output)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Create diff overlay: dim the candidate image and highlight differences in magenta
        diff_img = cand_img.copy()
        diff_pix = cast(Any, diff_img.load())

        # Dim background
        for y in range(max_h):
            for x in range(max_w):
                r, g, b, a = diff_pix[x, y]
                diff_pix[x, y] = (int(r * 0.4), int(g * 0.4), int(b * 0.4), a)

        # Highlight diffs in magenta (255, 0, 128)
        for x, y in diff_mask:
            diff_pix[x, y] = (255, 0, 128, 255)

        diff_img.save(out_path, format="PNG")
        saved_diff_path = str(out_path)

    return VisualDiffResult(
        baseline_path=str(base_file),
        candidate_path=str(cand_file),
        diff_path=saved_diff_path,
        total_pixels=total_pixels,
        diff_pixels=diff_pixels,
        diff_percentage=diff_percentage,
        passed=passed,
    )
