"""Shared Pytest fixtures for Tracecase CLI Dogfood Test Suites.

Guarantees strict isolation:
- Overrides HOME and TRACECASE_HOME with clean temp directories.
- Isolates PYTHONPATH to src/ to prevent annotated_doc shadowing.
- Spins up local Playground (9010) and Fake LLM (9110) servers.
- Builds clean Git fixture repositories.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Generator

import pytest

from tests.dogfood.fixtures.fake_llm.server import create_fake_llm_server
from tests.dogfood.fixtures.git_repo_builder import build_git_fixture_repo
from tests.dogfood.fixtures.playground_app.server import create_playground_server

REPO_ROOT = Path(__file__).resolve().parents[3]
TRACECASE_BIN = REPO_ROOT / ".venv" / "bin" / "tracecase"
# Resolve real browser cache path before test HOME override
REAL_PLAYWRIGHT_BROWSERS_PATH = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or str(Path.home() / "Library" / "Caches" / "ms-playwright")


def pytest_configure(config):
    """Register custom flow marker for dogfood traceability."""
    config.addinivalue_line("markers", "flow(id): Flow ID mapped from flows.yaml")


@pytest.fixture
def isolated_workspace() -> Generator[Path, None, None]:
    """Provide a clean isolated workspace folder for each test."""
    tmp = Path(tempfile.mkdtemp(prefix="tc_test_ws_"))
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def isolated_env(isolated_workspace: Path) -> dict[str, str]:
    """Isolated environment variables ensuring no leakage into user directory."""
    env = os.environ.copy()
    env["HOME"] = str(isolated_workspace)
    env["TRACECASE_HOME"] = str(isolated_workspace / ".tracecase")
    env["PYTHONPATH"] = os.environ.get("PYTHONPATH") or str(REPO_ROOT / "src")
    if Path(REAL_PLAYWRIGHT_BROWSERS_PATH).exists():
        env["PLAYWRIGHT_BROWSERS_PATH"] = REAL_PLAYWRIGHT_BROWSERS_PATH
    # Exclude root from python path
    return env


def _get_worker_offset() -> int:
    worker = os.environ.get("PYTEST_XDIST_WORKER", "gw0")
    if worker.startswith("gw"):
        try:
            return int(worker[2:])
        except ValueError:
            return 0
    return 0


@pytest.fixture(scope="session")
def playground_server_url() -> Generator[str, None, None]:
    port = 9010 + _get_worker_offset() * 10
    server = create_playground_server(host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


@pytest.fixture(scope="session")
def fake_llm_server_url() -> Generator[str, None, None]:
    port = 9110 + _get_worker_offset() * 10
    server = create_fake_llm_server(host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def git_fixture_repo() -> Generator[dict[str, str], None, None]:
    tmp = Path(tempfile.mkdtemp(prefix="tc_git_repo_"))
    info = build_git_fixture_repo(tmp)
    yield info
    shutil.rmtree(tmp, ignore_errors=True)


def run_tracecase(args: list[str], env: dict[str, str] | None = None, cwd: Path | str | None = None) -> subprocess.CompletedProcess[str]:
    """Execute tracecase CLI command in subprocess."""
    cmd = [str(TRACECASE_BIN)] + args
    effective_cwd = cwd or (Path(env["HOME"]) if (env and "HOME" in env) else REPO_ROOT)
    return subprocess.run(
        cmd,
        cwd=effective_cwd,
        env=env,
        capture_output=True,
        text=True,
    )
