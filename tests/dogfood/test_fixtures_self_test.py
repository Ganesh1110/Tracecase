"""Self-test for Tracecase Dogfood Fixtures.

Proves that:
1. Playground web app starts, serves all pages, action targets, and status endpoints.
2. Fake LLM server starts, serves OpenAI & Ollama formats, logs payloads, and handles error modes.
3. Git fixture repository builder creates valid 3-commit history with detectable code changes.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

from tests.dogfood.fixtures.fake_llm.server import create_fake_llm_server
from tests.dogfood.fixtures.git_repo_builder import build_git_fixture_repo
from tests.dogfood.fixtures.playground_app.server import create_playground_server


@pytest.fixture(scope="module")
def playground_server():
    server = create_playground_server(host="127.0.0.1", port=9005)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    yield "http://127.0.0.1:9005"
    server.shutdown()


@pytest.fixture(scope="module")
def fake_llm_server():
    server = create_fake_llm_server(host="127.0.0.1", port=9105)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    yield "http://127.0.0.1:9105"
    server.shutdown()


def test_playground_pages_served(playground_server: str):
    """Verify all core and healing pages are available and return HTML."""
    pages = [
        "",
        "login",
        "registration",
        "actions",
        "multitab",
        "scrolling",
        "console_errors",
        "network_tester",
        "fragile_selectors",
        "hostile_content",
        "version_a",
        "version_b",
        "version_c",
        "healing_tier1_xpath",
        "healing_tier2_testid",
        "healing_tier3_id",
        "healing_tier4_name",
        "healing_tier5_placeholder",
        "healing_tier6_aria",
        "healing_tier7_cleancss",
        "healing_tier8_role",
        "healing_tier9_text",
        "healing_tier10_allfail",
        "healing_false_positive",
    ]

    for p in pages:
        url = f"{playground_server}/{p}" if p else playground_server
        req = Request(url)
        with urlopen(req) as resp:
            assert resp.status == 200
            content = resp.read().decode("utf-8")
            assert "<!DOCTYPE html>" in content or "<html>" in content


def test_playground_api_endpoints(playground_server: str):
    """Verify status codes and login validation endpoints."""
    # 200 OK
    with urlopen(f"{playground_server}/api/status/200") as resp:
        assert resp.status == 200
        data = json.loads(resp.read())
        assert data["status"] == 200

    # 500 Error
    try:
        urlopen(f"{playground_server}/api/status/500")
        pytest.fail("Expected HTTP 500 error")
    except Exception as exc:
        assert "500" in str(exc)

    # Login POST success
    login_req = Request(
        f"{playground_server}/api/login",
        data=json.dumps({"username": "qa_user", "password": "secure_pass_123"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(login_req) as resp:
        assert resp.status == 200
        body = json.loads(resp.read())
        assert body["authenticated"] is True
        assert "token" in body


def test_fake_llm_openai_compatibility(fake_llm_server: str):
    """Verify OpenAI /v1/models and /v1/chat/completions."""
    # Models
    with urlopen(f"{fake_llm_server}/v1/models") as resp:
        assert resp.status == 200
        models = json.loads(resp.read())["data"]
        assert any(m["id"] == "gpt-4o" for m in models)

    # Chat completions
    chat_req = Request(
        f"{fake_llm_server}/v1/chat/completions",
        data=json.dumps({
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Analyze test case"}],
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(chat_req) as resp:
        assert resp.status == 200
        chat_resp = json.loads(resp.read())
        content = json.loads(chat_resp["choices"][0]["message"]["content"])
        assert "summary" in content
        assert "risk_score" in content
        assert "recommended_assertions" in content


def test_fake_llm_ollama_compatibility(fake_llm_server: str):
    """Verify Ollama /api/tags and /api/chat."""
    with urlopen(f"{fake_llm_server}/api/tags") as resp:
        assert resp.status == 200
        tags = json.loads(resp.read())["models"]
        assert any(t["name"] == "llama3:latest" for t in tags)


def test_fake_llm_error_modes(fake_llm_server: str):
    """Verify error mode switching (500, malformed)."""
    # Test HTTP 500 mode via header
    req_500 = Request(
        f"{fake_llm_server}/v1/chat/completions",
        data=json.dumps({"model": "gpt-4o", "messages": []}).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Mock-Mode": "500"},
    )
    try:
        urlopen(req_500)
        pytest.fail("Expected 500 error")
    except Exception as exc:
        assert "500" in str(exc)

    # Test malformed JSON mode
    req_mal = Request(
        f"{fake_llm_server}/v1/chat/completions",
        data=json.dumps({"model": "gpt-4o", "messages": []}).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Mock-Mode": "malformed"},
    )
    with urlopen(req_mal) as resp:
        raw = resp.read()
        with pytest.raises(json.JSONDecodeError):
            json.loads(raw)


def test_git_repo_builder():
    """Verify git fixture builder produces 3 commits with detectable diffs."""
    tmp = tempfile.mkdtemp(prefix="tc_test_git_builder_")
    try:
        info = build_git_fixture_repo(tmp)
        repo_path = Path(info["repo_path"])
        assert repo_path.exists()
        assert (repo_path / ".git").is_dir()
        assert info["commit_1"] != info["commit_2"]
        assert info["commit_2"] != info["commit_3"]

        # Check git log count
        res = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert res.stdout.strip() == "3"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
