# Visual Regression Testing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide pixel-accurate visual regression testing for QA Auto, comparing replayed or run-time screenshots against baseline recording screenshots, calculating difference metrics, producing highlighted diff images, and integrating with `replay` and a new `diff` CLI command.

**Architecture:** Add `qa_auto.replay.visual` with `compare_images` and `VisualDiffResult`. Integrate into `ReplayEngine` when `--diff` / `--visual-diff` is active. Provide a standalone `qa_auto diff` CLI command.

**Tech Stack:** Python 3.13, Pillow (PIL), Typer, Rich, Playwright async API.

## Global Constraints

- Python `>=3.13`, Ruff `target-version = "py313"`, line length 100.
- Core dependencies: Pillow (already in `pyproject.toml`).
- Offline by default. Tests must use `127.0.0.1` or in-memory images.
- `testcase.json` schema remains immutable. Replay and diff results are stored in `replay.json` or diff output directories.
- Exit codes: `0` on success (within threshold), `1` on visual diff failure (exceeds threshold), `2` on missing files / infrastructure errors.
- Ruff rules: `E`, `F`, `I`, `UP`, `B`, `SIM`. Strict typing (`disallow_untyped_defs`).

---

### Task 1: Image diff algorithm & visual diff metrics

**Files:**
- Create: `src/qa_auto/replay/visual.py`
- Test: `tests/replay/test_visual_diff.py`

**Interfaces:**
- Produces:
  - `VisualDiffResult` (Pydantic model or dataclass):
    - `baseline_path: str`
    - `candidate_path: str`
    - `diff_path: str | None`
    - `total_pixels: int`
    - `diff_pixels: int`
    - `diff_percentage: float`
    - `passed: bool`
  - `compare_images(baseline: Path | str, candidate: Path | str, diff_output: Path | str | None = None, threshold_percent: float = 0.1) -> VisualDiffResult`

- [ ] **Step 1: Write failing visual diff unit tests**

Create `tests/replay/test_visual_diff.py`:
- Test identical images: 0 diff pixels, 0.0% diff, passed=True.
- Test modified image: detect changed pixels, produce highlighted diff image, passed=False when threshold exceeded.
- Test different dimensions: handles size mismatch gracefully (e.g. pads to larger canvas or measures difference across union).
- Test threshold tolerance: diffs within custom `threshold_percent` pass.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/replay/test_visual_diff.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'qa_auto.replay.visual'`.

- [ ] **Step 3: Implement `src/qa_auto/replay/visual.py`**

- Use PIL to load images, convert to RGBA.
- Handle dimension mismatches by creating a composite bounding canvas.
- Compute channel deltas per pixel; if Euclidean or absolute RGB delta > tolerance, flag as diff pixel.
- Generate diff image highlighting differences with magenta overlay `(255, 0, 128, 255)` on dim baseline.
- Return `VisualDiffResult`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/replay/test_visual_diff.py -v`
Expected: all tests pass.

- [ ] **Step 5: Run lint and types**

Run: `ruff check src/qa_auto/replay/visual.py tests/replay/test_visual_diff.py && mypy src/qa_auto --ignore-missing-imports`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/qa_auto/replay/visual.py tests/replay/test_visual_diff.py
git commit -m "Add visual diff comparison engine using Pillow"
```

---

### Task 2: Replay engine visual diff integration

**Files:**
- Modify: `src/qa_auto/replay/models.py`
- Modify: `src/qa_auto/replay/engine.py`
- Test: `tests/integration/test_replay_visual.py`

**Interfaces:**
- Add `visual_diffs: list[VisualDiffResult] = []` to `ReplayResult` in `src/qa_auto/replay/models.py`.
- In `ReplayEngine.replay(...)`:
  - When `visual_diff: bool = False` is set, after executing each step, take a screenshot of the candidate state.
  - Compare against the step's recorded baseline screenshot (if present).
  - Store diff images in `<output_dir>/diffs/`.
  - Append `VisualDiffResult` to `ReplayResult.visual_diffs`.
  - If any visual diff fails (exceeds threshold) and `visual_fail: bool = False` is enabled, mark `ReplayResult.passed = False`.

- [ ] **Step 1: Write failing replay visual diff integration test**

Create `tests/integration/test_replay_visual.py`:
- Replay test case with `visual_diff=True`.
- Verify diffs are calculated and saved to output directory.

- [ ] **Step 2: Run tests to verify failure**

- [ ] **Step 3: Update `ReplayResult` and `ReplayEngine`**

- [ ] **Step 4: Run tests to verify pass**

- [ ] **Step 5: Lint and types**

- [ ] **Step 6: Commit**

```bash
git add src/qa_auto/replay/models.py src/qa_auto/replay/engine.py tests/integration/test_replay_visual.py
git commit -m "Integrate visual diffing into replay engine"
```

---

### Task 3: CLI commands: `qa_auto diff` and `qa_auto replay --diff`

**Files:**
- Modify: `src/qa_auto/cli.py`
- Test: `tests/test_cli_diff.py`

**Interfaces:**
- CLI command: `qa_auto diff <baseline> <candidate> [--threshold 0.1] [--output <dir>]`
  - Accepts image paths OR directories containing screenshots/testcase.json.
- CLI flags in `qa_auto replay`:
  - `--diff` / `--no-diff`: enable visual screenshot comparison during replay.
  - `--diff-threshold <float>`: tolerance percentage (default: 0.1%).
  - `--diff-fail` / `--no-diff-fail`: fail replay if visual diff exceeds threshold.

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_cli_diff.py`:
- Test `qa_auto diff img1.png img2.png`.
- Test `qa_auto replay testcase.json --diff`.

- [ ] **Step 2: Run tests to verify failure**

- [ ] **Step 3: Update `src/qa_auto/cli.py`**

- [ ] **Step 4: Run tests to verify pass**

- [ ] **Step 5: Lint and types**

- [ ] **Step 6: Commit**

```bash
git add src/qa_auto/cli.py tests/test_cli_diff.py
git commit -m "Add diff CLI command and replay visual diff flags"
```

---

### Task 4: Documentation and phase verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document `qa_auto diff` and `--diff` flags in `README.md`**
- [ ] **Step 2: Run full test suite and quality gate**
- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Document visual regression testing capabilities"
```
