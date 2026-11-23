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
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["PLAYWRIGHT_BROWSERS_PATH"] = os.path.expanduser("~/Library/Caches/ms-playwright")
    # Exclude root from python path
    return env


@pytest.fixture(scope="session")
def playground_server_url() -> Generator[str, None, None]:
    server = create_playground_server(host="127.0.0.1", port=9010)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)
    yield "http://127.0.0.1:9010"
    server.shutdown()


@pytest.fixture(scope="session")
def fake_llm_server_url() -> Generator[str, None, None]:
    server = create_fake_llm_server(host="127.0.0.1", port=9110)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)
    yield "http://127.0.0.1:9110"
    server.shutdown()


@pytest.fixture
def git_fixture_repo() -> Generator[dict[str, str], None, None]:
    tmp = Path(tempfile.mkdtemp(prefix="tc_git_repo_"))
    info = build_git_fixture_repo(tmp)
    yield info
    shutil.rmtree(tmp, ignore_errors=True)


def run_tracecase(args: list[str], env: dict[str, str] | None = None, cwd: Path | str | None = None) -> subprocess.CompletedProcess[str]:
    """Execute tracecase CLI command in subprocess."""
    cmd = [str(TRACECASE_BIN)] + args
    return subprocess.run(
        cmd,
        cwd=cwd or REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
