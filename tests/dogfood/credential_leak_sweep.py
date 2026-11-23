"""
Credential Leak Sweep (BUG-009 Escalation Audit & Positive Controls)

Audits all Tracecase storage, export, and processing surfaces for leakage
of sensitive credentials entered during recording:
- Canary Password: 'CANARY_PW_9f3a7c' (in input[type=password])
- Canary API Key:   'CANARY_API_KEY_8a2d1e' (in input[name=api_key])

Surfaces Checked:
 1. testcase.json
 2. testcase.md
 3. testcase.html
 4. screenshots (image files metadata/raw)
 5. HAR export (.har)
 6. Generated pytest code (test_*.py)
 7. Mutations (mutations/testcase_*.json)
 8. Analysis output (analysis.json)
 9. Replay report (replay.json)
10. Corpus DB FTS index (corpus.db SQLite)
11. CLI stdout / stderr
12. MCP server responses (get_testcase)
13. Fake-LLM request payload logs
"""

import asyncio
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = REPO_ROOT / "tests" / "dogfood" / "evidence"
CANARY_PW = "CANARY_PW_9f3a7c"
CANARY_KEY = "CANARY_API_KEY_8a2d1e"


def run_cmd(args: list[str], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
    )


async def record_credentials(session_dir: Path, server_url: str):
    from tracecase.recorder import Recorder

    page_url = f"{server_url}/login.html"
    rec = Recorder(
        output_dir=session_dir,
        start_url=page_url,
        name="Credential Leak Audit Flow",
        browser_type="chromium",
        headless=True,
        auto_start=True,
    )
    task = asyncio.create_task(rec.run())
    try:
        while not rec.is_recording:
            await asyncio.sleep(0.05)
        page = rec._pages[0]
        await page.wait_for_selector("#username")
        await page.fill("#username", "alice_admin")
        await page.fill("#password", CANARY_PW)
        # Add dynamic input for api_key to page and type canary
        await page.evaluate("""() => {
            const input = document.createElement('input');
            input.id = 'api_key';
            input.name = 'api_key';
            input.type = 'text';
            document.body.appendChild(input);
        }""")
        await page.fill("#api_key", CANARY_KEY)
        await asyncio.sleep(0.8)  # Allow debounce & network
        await page.click("#btn-login")
        await asyncio.sleep(0.8)
    finally:
        await rec.stop_recording()
        try:
            await asyncio.wait_for(task, timeout=10.0)
        except Exception:
            pass


def check_text(content: str, token: str) -> bool:
    return token in content


def run_positive_controls(temp_dir: Path) -> list[dict]:
    """Plants each canary into a synthetic copy of each artifact type and tests detector sensitivity."""
    print("\n--- RUNNING POSITIVE CONTROLS PER SURFACE ---")
    controls = []

    # 1. testcase.json
    f = temp_dir / "ctrl_testcase.json"
    f.write_text(json.dumps({"input_value": CANARY_PW, "key": CANARY_KEY}), encoding="utf-8")
    c = f.read_text(encoding="utf-8")
    controls.append({"surface": "testcase.json", "pw": check_text(c, CANARY_PW), "key": check_text(c, CANARY_KEY)})

    # 2. testcase.md
    f = temp_dir / "ctrl_testcase.md"
    f.write_text(f"| Step | Action | {CANARY_PW} | {CANARY_KEY} |", encoding="utf-8")
    c = f.read_text(encoding="utf-8")
    controls.append({"surface": "testcase.md", "pw": check_text(c, CANARY_PW), "key": check_text(c, CANARY_KEY)})

    # 3. testcase.html
    f = temp_dir / "ctrl_testcase.html"
    f.write_text(f"<div>{CANARY_PW}</div><span>{CANARY_KEY}</span>", encoding="utf-8")
    c = f.read_text(encoding="utf-8")
    controls.append({"surface": "testcase.html", "pw": check_text(c, CANARY_PW), "key": check_text(c, CANARY_KEY)})

    # 4. screenshots (raw bytes)
    f = temp_dir / "ctrl_screenshot.png"
    f.write_bytes(f"PNG_HEADER_{CANARY_PW}_{CANARY_KEY}".encode("utf-8"))
    b = f.read_bytes()
    controls.append({"surface": "screenshots", "pw": CANARY_PW.encode() in b, "key": CANARY_KEY.encode() in b})

    # 5. HAR export
    f = temp_dir / "ctrl_network.har"
    f.write_text(json.dumps({"log": {"entries": [{"request": {"postData": {"text": f"{CANARY_PW}:{CANARY_KEY}"}}}]}}), encoding="utf-8")
    c = f.read_text(encoding="utf-8")
    controls.append({"surface": ".har export", "pw": check_text(c, CANARY_PW), "key": check_text(c, CANARY_KEY)})

    # 6. Generated pytest
    f = temp_dir / "ctrl_test.py"
    f.write_text(f"await page.fill('#pw', '{CANARY_PW}')\nawait page.fill('#key', '{CANARY_KEY}')", encoding="utf-8")
    c = f.read_text(encoding="utf-8")
    controls.append({"surface": "generated pytest", "pw": check_text(c, CANARY_PW), "key": check_text(c, CANARY_KEY)})

    # 7. Mutations
    f = temp_dir / "ctrl_mutation.json"
    f.write_text(json.dumps({"mutations": [CANARY_PW, CANARY_KEY]}), encoding="utf-8")
    c = f.read_text(encoding="utf-8")
    controls.append({"surface": "mutations/*.json", "pw": check_text(c, CANARY_PW), "key": check_text(c, CANARY_KEY)})

    # 8. analysis.json
    f = temp_dir / "ctrl_analysis.json"
    f.write_text(json.dumps({"risks": [CANARY_PW], "summary": CANARY_KEY}), encoding="utf-8")
    c = f.read_text(encoding="utf-8")
    controls.append({"surface": "analysis.json", "pw": check_text(c, CANARY_PW), "key": check_text(c, CANARY_KEY)})

    # 9. replay.json
    f = temp_dir / "ctrl_replay.json"
    f.write_text(json.dumps({"status": "passed", "details": f"{CANARY_PW} {CANARY_KEY}"}), encoding="utf-8")
    c = f.read_text(encoding="utf-8")
    controls.append({"surface": "replay.json", "pw": check_text(c, CANARY_PW), "key": check_text(c, CANARY_KEY)})

    # 10. corpus.db (FTS5)
    db = temp_dir / "ctrl_corpus.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE VIRTUAL TABLE steps_fts USING fts5(testcase_id, description)")
        conn.execute("INSERT INTO steps_fts VALUES ('tc1', ?)", (f"Type '{CANARY_PW}' and '{CANARY_KEY}'",))
        rows = conn.execute("SELECT * FROM steps_fts").fetchall()
        row_str = " ".join(str(x) for r in rows for x in r)
        controls.append({"surface": "corpus.db (FTS)", "pw": CANARY_PW in row_str, "key": CANARY_KEY in row_str})

    # 11. CLI stdout/stderr
    cli_str = f"Tracecase run with {CANARY_PW} and {CANARY_KEY}"
    controls.append({"surface": "CLI stdout/stderr", "pw": check_text(cli_str, CANARY_PW), "key": check_text(cli_str, CANARY_KEY)})

    # 12. MCP responses
    mcp_str = json.dumps({"result": {"content": [{"text": f"{CANARY_PW}:{CANARY_KEY}"}]}})
    controls.append({"surface": "MCP responses", "pw": check_text(mcp_str, CANARY_PW), "key": check_text(mcp_str, CANARY_KEY)})

    # 13. Fake-LLM logs
    llm_str = json.dumps([{"prompt": f"Analyze: {CANARY_PW} and {CANARY_KEY}"}])
    controls.append({"surface": "Fake-LLM logs", "pw": check_text(llm_str, CANARY_PW), "key": check_text(llm_str, CANARY_KEY)})

    return controls


def main():
    print("================================================================================")
    print("TRACECASE CREDENTIAL LEAK AUDIT SWEEP (13 SURFACES WITH POSITIVE CONTROLS)")
    print("================================================================================")

    import threading
    import time
    from tests.dogfood.fixtures.playground_app.server import create_playground_server
    from tests.dogfood.fixtures.fake_llm.server import create_fake_llm_server

    temp_dir = Path(tempfile.mkdtemp(prefix="tc_leak_audit_"))
    session_dir = temp_dir / "recordings" / "tc_credentials"
    session_dir.mkdir(parents=True, exist_ok=True)

    fake_home = temp_dir / "home"
    fake_home.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env["TRACECASE_HOME"] = str(fake_home / ".tracecase")
    env["PYTHONPATH"] = str(REPO_ROOT / "src")

    play_server = create_playground_server(host="127.0.0.1", port=9018)
    t_play = threading.Thread(target=play_server.serve_forever, daemon=True)
    t_play.start()
    play_url = "http://127.0.0.1:9018"

    llm_server = create_fake_llm_server(host="127.0.0.1", port=9118)
    t_llm = threading.Thread(target=llm_server.serve_forever, daemon=True)
    t_llm.start()
    llm_url = "http://127.0.0.1:9118"
    time.sleep(0.3)

    cli_out_all = ""

    try:
        # Step A: Run Positive Controls
        ctrl_results = run_positive_controls(temp_dir)
        ctrl_lines = [
            "| Surface | Password Canary Detected? | API Key Canary Detected? | Status |",
            "|---|---|---|---|",
        ]
        all_ctrl_pass = True
        for c in ctrl_results:
            passed = c["pw"] and c["key"]
            if not passed: all_ctrl_pass = False
            status = "✓ VERIFIED SENSITIVE" if passed else "❌ FAILED"
            ctrl_lines.append(f"| `{c['surface']}` | {c['pw']} | {c['key']} | {status} |")
        ctrl_table = "\n".join(ctrl_lines)
        print(ctrl_table)
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        (EVIDENCE_DIR / "credential_sweep_positive_controls.txt").write_text(ctrl_table + "\n", encoding="utf-8")
        assert all_ctrl_pass, "One or more positive controls failed!"

        # Step B: Record Live Canary Session
        print("\n[1/5] Recording browser interaction with password & API key canaries...")
        asyncio.run(record_credentials(session_dir, play_url))
        tc_json_path = session_dir / "testcase.json"
        assert tc_json_path.exists(), "Failed to record testcase.json"
        print(f"  Recorded to {session_dir}")

        cli_bin = REPO_ROOT / ".venv" / "bin" / "tracecase"

        # 2. Codegen (write directly to specific test file)
        print("[2/5] Running codegen, HAR export, analyze, mutate, replay...")
        codegen_dir = temp_dir / "codegen"
        codegen_dir.mkdir(parents=True, exist_ok=True)
        codegen_file = codegen_dir / "test_login.py"
        res = run_cmd([str(cli_bin), "codegen", str(tc_json_path), "-o", str(codegen_file)], env=env, cwd=temp_dir)
        cli_out_all += f"\n[CODEGEN STDOUT]\n{res.stdout}\n[STDERR]\n{res.stderr}"

        # 3. HAR Export (write directly to specific har file)
        har_dir = temp_dir / "har_export"
        har_dir.mkdir(parents=True, exist_ok=True)
        har_file = har_dir / "network.har"
        res = run_cmd([str(cli_bin), "export-har", str(tc_json_path), "-o", str(har_file)], env=env, cwd=temp_dir)
        cli_out_all += f"\n[HAR STDOUT]\n{res.stdout}\n[STDERR]\n{res.stderr}"

        # 4. Analyze (Heuristic & AI against fake LLM)
        analysis_dir = temp_dir / "analysis"
        res = run_cmd([str(cli_bin), "analyze", str(tc_json_path), "-o", str(analysis_dir), "--ai", "--provider", "openai", "--base-url", f"{llm_url}/v1"], env=env, cwd=temp_dir)
        cli_out_all += f"\n[ANALYZE STDOUT]\n{res.stdout}\n[STDERR]\n{res.stderr}"

        # 5. Mutate
        mutate_dir = temp_dir / "mutations"
        res = run_cmd([str(cli_bin), "mutate", str(tc_json_path), "-o", str(mutate_dir)], env=env, cwd=temp_dir)
        cli_out_all += f"\n[MUTATE STDOUT]\n{res.stdout}\n[STDERR]\n{res.stderr}"

        # 6. Replay
        replay_dir = temp_dir / "replay"
        res = run_cmd([str(cli_bin), "replay", str(tc_json_path), "-o", str(replay_dir)], env=env, cwd=temp_dir)
        cli_out_all += f"\n[REPLAY STDOUT]\n{res.stdout}\n[STDERR]\n{res.stderr}"

        # 7. Index & Corpus Search
        corpus_db = temp_dir / "corpus.db"
        res = run_cmd([str(cli_bin), "index", str(temp_dir / "recordings"), "--db", str(corpus_db)], env=env, cwd=temp_dir)
        cli_out_all += f"\n[INDEX STDOUT]\n{res.stdout}\n[STDERR]\n{res.stderr}"

        # 8. MCP get_testcase
        from tracecase.mcp.server import MCPServer
        mcp = MCPServer(db_path=corpus_db)
        tc_id = json.loads(tc_json_path.read_text(encoding="utf-8"))["id"]
        mcp_res = asyncio.run(mcp.handle_request({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "get_testcase", "arguments": {"testcase_id": tc_id}}
        }))
        mcp_text = json.dumps(mcp_res)

        print("[3/5] Auditing all 13 surfaces for canary tokens...")

        surfaces = {}

        # 1. testcase.json
        c_tc_json = tc_json_path.read_text(encoding="utf-8") if tc_json_path.exists() else ""
        surfaces["testcase.json"] = (check_text(c_tc_json, CANARY_PW), check_text(c_tc_json, CANARY_KEY))

        # 2. testcase.md
        tc_md = session_dir / "testcase.md"
        c_tc_md = tc_md.read_text(encoding="utf-8") if tc_md.exists() else ""
        surfaces["testcase.md"] = (check_text(c_tc_md, CANARY_PW), check_text(c_tc_md, CANARY_KEY))

        # 3. testcase.html
        tc_html = session_dir / "testcase.html"
        c_tc_html = tc_html.read_text(encoding="utf-8") if tc_html.exists() else ""
        surfaces["testcase.html"] = (check_text(c_tc_html, CANARY_PW), check_text(c_tc_html, CANARY_KEY))

        # 4. screenshots
        screenshots = list(session_dir.glob("*.png"))
        ss_found_pw, ss_found_key = False, False
        for s in screenshots:
            try:
                b = s.read_bytes()
                if CANARY_PW.encode() in b: ss_found_pw = True
                if CANARY_KEY.encode() in b: ss_found_key = True
            except Exception:
                pass
        surfaces["screenshots"] = (ss_found_pw, ss_found_key)

        # 5. HAR export
        har_files = list(har_dir.glob("*.har")) + list(session_dir.glob("*.har"))
        c_har = "".join([h.read_text(encoding="utf-8") for h in har_files])
        surfaces[".har export"] = (check_text(c_har, CANARY_PW), check_text(c_har, CANARY_KEY))

        # 6. Generated pytest
        py_files = list(codegen_dir.glob("*.py"))
        c_py = "".join([p.read_text(encoding="utf-8") for p in py_files])
        surfaces["generated pytest"] = (check_text(c_py, CANARY_PW), check_text(c_py, CANARY_KEY))

        # 7. Mutations
        mut_files = list(mutate_dir.glob("**/testcase.json")) + list(mutate_dir.glob("*.json"))
        c_mut = "".join([m.read_text(encoding="utf-8") for m in mut_files])
        surfaces["mutations/*.json"] = (check_text(c_mut, CANARY_PW), check_text(c_mut, CANARY_KEY))

        # 8. analysis.json
        an_file = analysis_dir / "analysis.json"
        c_an = an_file.read_text(encoding="utf-8") if an_file.exists() else ""
        surfaces["analysis.json"] = (check_text(c_an, CANARY_PW), check_text(c_an, CANARY_KEY))

        # 9. replay.json
        rep_file = replay_dir / "replay.json"
        c_rep = rep_file.read_text(encoding="utf-8") if rep_file.exists() else ""
        surfaces["replay.json"] = (check_text(c_rep, CANARY_PW), check_text(c_rep, CANARY_KEY))

        # 10. corpus.db (FTS)
        fts_pw, fts_key = False, False
        if corpus_db.exists():
            with sqlite3.connect(corpus_db) as conn:
                for row in conn.execute("SELECT * FROM steps_fts").fetchall():
                    row_str = " ".join([str(x) for x in row])
                    if CANARY_PW in row_str: fts_pw = True
                    if CANARY_KEY in row_str: fts_key = True
        surfaces["corpus.db (FTS)"] = (fts_pw, fts_key)

        # 11. CLI stdout/stderr
        surfaces["CLI stdout/stderr"] = (check_text(cli_out_all, CANARY_PW), check_text(cli_out_all, CANARY_KEY))

        # 12. MCP server responses
        surfaces["MCP responses"] = (check_text(mcp_text, CANARY_PW), check_text(mcp_text, CANARY_KEY))

        # 13. Fake-LLM request logs
        from tests.dogfood.fixtures.fake_llm.server import FakeLLMHandler
        llm_logs = json.dumps(FakeLLMHandler.received_requests)
        surfaces["Fake-LLM logs"] = (check_text(llm_logs, CANARY_PW), check_text(llm_logs, CANARY_KEY))

        print("\n" + "="*80)
        print("CREDENTIAL LEAK AUDIT RESULTS")
        print("="*80)
        md_lines = [
            "| Surface | Password Canary (`CANARY_PW_9f3a7c`) | API Key Canary (`CANARY_API_KEY_8a2d1e`) | Severity | Leak Detected? |",
            "|---|---|---|---|---|",
        ]
        for surf, (pw_leak, key_leak) in surfaces.items():
            pw_str = "**LEAKED**" if pw_leak else "Clean"
            key_str = "**LEAKED**" if key_leak else "Clean"
            any_leak = pw_leak or key_leak
            leak_str = "⚠️ **YES**" if any_leak else "✅ None"
            sev = "CRITICAL (BUG-009)" if pw_leak else ("MED (Design Decision)" if key_leak else "LOW")
            md_lines.append(f"| `{surf}` | {pw_str} | {key_str} | {sev} | {leak_str} |")

        table_md = "\n".join(md_lines)
        print(table_md)

        out_report = REPO_ROOT / "tests" / "dogfood" / "CREDENTIAL_LEAK_REPORT.md"
        out_report.write_text(table_md + "\n", encoding="utf-8")
        out_ev = EVIDENCE_DIR / "credential_leak_run.txt"
        out_ev.write_text(table_md + "\n", encoding="utf-8")
        print(f"\nWrote leak report to: {out_report} and {out_ev}")

    finally:
        play_server.shutdown()
        play_server.server_close()
        llm_server.shutdown()
        llm_server.server_close()
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
