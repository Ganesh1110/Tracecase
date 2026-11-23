# Recording Scripts & Feasibility Analysis (RECORDING_SCRIPTS.md)

## 1. Feasibility Analysis

### A. Programmatic Recording of Web Applications
- **Approach Verified**:
  We ran a feasibility test driving the Tracecase `Recorder` class programmatically in headless mode.
  - The browser launches via `recorder.run()` in an asyncio task.
  - The control panel is injected as a DOM container with id `#__tracecase_panel__`.
  - The Start button has ID `#__qa_start_btn__` and Stop button has ID `#__qa_stop_btn__`.
  - The test code can await `page.click('#__qa_start_btn__')` to trigger `window.__tracecase_start_recording()`.
  - Subsequent Playwright actions (`page.click()`, `page.fill()`) on the target application fire the injected DOM event listeners, capturing steps, bounding boxes, element metadata, console messages, network calls, and screenshot highlights.
  - Calling `page.click('#__qa_stop_btn__')` triggers `window.__tracecase_stop_recording()`, exports `testcase.json`, `testcase.md`, and `testcase.html`, and closes the browser cleanly.
- **Verdict**: Fully automatable without human interaction for all standard CLI and web recording flows.

### B. Nested Recording (Recording Studio's Browser Recorder Page)
- **Feasibility Findings**:
  - Studio's Browser Recorder page (`http://127.0.0.1:8000/recorder`) controls a server-side recording session via FastAPI endpoints:
    - `POST /api/record/start`
    - `GET /api/record/status`
    - `POST /api/record/pause`
    - `POST /api/record/resume`
    - `POST /api/record/stop`
  - When Browser 1 (Tracecase outer recorder) records Studio's Recorder page:
    1. Browser 1 enters URL `http://127.0.0.1:9000/` into the Studio URL input and selects Chromium.
    2. Browser 1 clicks "Start Recording". Studio makes `POST /api/record/start`.
    3. Studio backend launches Browser 2 (inner browser instance) pointing to the target URL.
    4. Browser 1 observes Studio's UI transitioning to "Recording active" and displaying streaming steps via WebSocket.
    5. In an automated test, Browser 2 would remain on its start page unless interacted with.
    6. Browser 1 clicks "Stop Recording" in Studio. Studio makes `POST /api/record/stop`, finalizing the inner testcase.
    7. Outer Browser 1 clicks its own `#` `__qa_stop_btn__` to finalize the recording of the Studio UI.
- **Verdict**:
  - **Automated**: The outer recording of Studio UI launching, streaming status, pausing, and stopping can be automated completely by having the outer driver interact with Studio's UI controls.
  - **Human-Assisted Alternative**: For flows where a human tester wants to visually verify multi-window interaction during headed nested recording, the manual click-by-click script below is provided.

---

## 2. Click-by-Click Instructions for Human-Assisted Recording Flows [HUMAN-RECORD]

If any flow requires manual execution or visual audit (e.g. physical multi-monitor verification or manual browser window interaction):

### Script HR-1: Nested Headed Recording in Studio (Flow L5 / B12)
1. Start Studio backend: `./scripts/start_backend.sh`
2. Start Studio frontend: `./scripts/start_frontend.sh`
3. Launch outer Tracecase CLI recorder against Studio:
   ```bash
   tracecase record http://localhost:3000/recorder -o ./recordings/studio_recorder_outer --name "Studio Recorder Flow"
   ```
4. In the outer browser window:
   - Click `▶ Start` in the top-right green Tracecase control panel.
   - Enter `http://127.0.0.1:9000/login` in the Target URL field.
   - Choose `Chromium` and uncheck `Headless`.
   - Click `Record Browser` / `Launch Recording`.
5. An inner browser window will appear on screen pointing to the login page:
   - Click `▶ Start` in the inner browser window's control panel.
   - Enter username `admin` and password `password123`.
   - Click `Log In`.
   - Click `⏹ Stop` in the inner browser window.
6. Return to the outer browser window:
   - Observe that the recorded steps have streamed into the Studio UI.
   - Click `⏹ Stop` in the outer Tracecase control panel.
7. Verification:
   - Outer recording directory contains `testcase.json` detailing the Studio UI clicks.
   - Studio's internal testcases table has registered the new login testcase.

### Script HR-2: Firefox / WebKit Headed Desktop Verification (Flow B5, B6)
1. Ensure Playwright browser binaries are installed:
   ```bash
   python -m playwright install firefox webkit
   ```
2. Run command:
   ```bash
   tracecase record https://demo.playwright.dev/todomvc/ -b firefox -o ./recordings/firefox_smoke --name "Firefox Smoke"
   ```
3. When the Firefox window opens:
   - Click `▶ Start` on the control panel.
   - Click the input field, type `Buy milk`, and press `Enter`.
   - Click `⏹ Stop` on the control panel.
4. Verify `testcase.json` contains browser: `"firefox"`.
