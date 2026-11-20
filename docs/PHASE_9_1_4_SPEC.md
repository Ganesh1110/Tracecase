# Phase 9.1.4 Specification: Tracecase Studio Draft Versioning, Embedded Recorder & Multi-Engine Automation Architecture

This document tracks the approved Phase 9.1.4 architectural specification and Codex implementation prompt.

## Key Decisions & Architectural Guardrails
1. **Authoritative Draft Lifecycle:**
   - Single source of truth: Extends existing `synthesized_drafts` and `draft_validations` rather than creating duplicate tables.
   - Immutable version snapshots with SHA-256 `content_hash` binding.
   - Editing a draft immediately invalidates prior approvals and requires revalidation.
   - Transactional and idempotent promotion to `TestCase` and `TestSuite`.
2. **Multi-Engine Core Abstraction (`src/tracecase/engines/`):**
   - Base engine contracts (`BaseAutomationEngine`, `BaseSession`, `BaseRecorder`, `BaseExecutor`).
   - Explicit capability states (`SUPPORTED`, `UNSUPPORTED`, `AVAILABLE_BUT_NOT_INSTALLED`, `REQUIRES_EXTERNAL_INFRASTRUCTURE`, `NOT_YET_IMPLEMENTED`).
   - Playwright is wrapped as the first operational engine without rewriting its existing core.
   - Selenium and Appium are stubbed with `NOT_YET_IMPLEMENTED` and deferred to dedicated expansion phases (A and B).
   - Clear distinction: Playwright WebKit is WebKit, not native Safari; iOS requires macOS and Xcode.
3. **Embedded Playwright Chromium Recorder in Studio:**
   - Managed headed Chromium session streaming frames and forwarding mouse/keyboard events over WebSockets.
   - Studio viewport renders inside `Recorder.jsx` with navigation bar and recording HUD.
   - Zero external OS windows; no silent fallbacks.
   - Logical isolation between interactive embedded recording and Phase 9.1.3 headless validation sandbox.

Full Codex implementation prompt:
See [`docs/superpowers/plans/2026-11-20-phase-9-1-4-codex-prompt.md`](file:///Users/ganeshjayaprakash/experimental/Tracecase/docs/superpowers/plans/2026-11-20-phase-9-1-4-codex-prompt.md).
