# Codex Usage Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows desktop widget that mirrors the Claude Usage Widget while reading the current Codex account's dynamic rate-limit data through Codex app-server.

**Architecture:** A typed Python package separates JSON boundary parsing, the app-server subprocess client, configuration, Windows integration, assets, and Tkinter presentation. `widget.pyw` is a minimal entry point. Data refresh happens on a worker thread and enters Tk only through `root.after`.

**Tech Stack:** Python 3.11+, tkinter, standard-library subprocess/json/threading, Pillow, pystray, pytest, basedpyright, ruff, uv.

## Global Constraints

- Windows 10/11 and an installed, ChatGPT-authenticated Codex are required.
- Do not read, write, log, or display Codex OAuth tokens, email, user ID, or account ID.
- Use `codex app-server --stdio` and `account/rateLimits/read`; do not call WHAM directly in production code.
- Display only rate-limit windows actually returned by Codex and classify them by duration, never by primary/secondary position.
- Preserve the reference widget's theme, transparency, mini mode, tray, smart top-most, drag, DPI, singleton, and pet behavior.
- Keep each Python source file at or below 250 nonblank noncomment lines except the pure embedded asset table.
- Follow red → green → refactor; every behavior function has a failing test first.
- Do not commit, push, deploy, install startup entries, or mutate the Codex account.

---

### Task 1: Typed usage model and parser

**Files:**
- Create: `codex_usage_widget/models.py`
- Create: `codex_usage_widget/parser.py`
- Test: `tests/test_parser.py`

**Interfaces:**
- Consumes: JSON-decoded app-server result from `account/rateLimits/read`.
- Produces: `parse_rate_limits(payload: JsonValue, fetched_at: datetime) -> UsageSnapshot`.

- [ ] **Step 1: Write failing parser tests** for weekly-only, 5-hour+weekly, additional limit IDs, missing windows, clamping, credits, and reset-credit count using Given/When/Then sections.
- [ ] **Step 2: Run `uv run pytest tests/test_parser.py -q`** and confirm failures are caused by missing parser modules.
- [ ] **Step 3: Implement frozen slotted models** `UsageWindow`, `CreditStatus`, and `UsageSnapshot`, plus a boundary parser that accepts JSON primitives, rejects malformed required fields with typed `UsagePayloadError`, and ignores unknown fields.
- [ ] **Step 4: Run `uv run pytest tests/test_parser.py -q`** and confirm all parser tests pass.
- [ ] **Step 5: Run `uv run basedpyright codex_usage_widget/models.py codex_usage_widget/parser.py`** and remove all type errors.

### Task 2: Codex app-server RPC client

**Files:**
- Create: `codex_usage_widget/rpc.py`
- Test: `tests/fixtures/fake_app_server.py`
- Test: `tests/test_rpc.py`

**Interfaces:**
- Consumes: an executable path resolved from `CODEX_EXE`, `shutil.which`, or `%LOCALAPPDATA%/OpenAI/Codex/bin/*/codex.exe`.
- Produces: `read_rate_limits(timeout_seconds: float = 20.0) -> RpcResult` where `RpcResult` is a discriminated union of success and typed failure dataclasses.

- [ ] **Step 1: Write failing RPC tests** against a fake JSONL process for notification interleaving, EOF, timeout, malformed JSON, missing executable, and successful response.
- [ ] **Step 2: Run `uv run pytest tests/test_rpc.py -q`** and confirm the client is missing.
- [ ] **Step 3: Implement executable discovery and one-shot subprocess handshake** using `subprocess.Popen`, background-safe blocking I/O, request ID matching, `initialize`, and `account/rateLimits/read`. Always terminate the child in a context-managed boundary.
- [ ] **Step 4: Run `uv run pytest tests/test_rpc.py -q`** and confirm all tests pass without network or real credentials.
- [ ] **Step 5: Run a real read-only integration command** against the installed Codex and confirm a response contains at least one normalized window or an actionable typed login error.

### Task 3: Configuration, Windows integration, and assets

**Files:**
- Create: `codex_usage_widget/config.py`
- Create: `codex_usage_widget/windows.py`
- Create: `codex_usage_widget/assets.py`
- Test: `tests/test_config.py`
- Test: `tests/test_windows.py`

**Interfaces:**
- Produces: `WidgetConfig`, atomic `load_config`/`save_config`, DPI helpers, singleton mutex, foreground process detection, z-order, taskbar hiding, and decoded pet/tray images.

- [ ] **Step 1: Write failing tests** for default merge, invalid JSON recovery, atomic save content, off-screen position recovery, and Codex foreground process classification.
- [ ] **Step 2: Run targeted tests** and confirm failures reflect missing production modules.
- [ ] **Step 3: Implement strict config parsing and Windows helpers**, reusing the reference behavior while naming Codex processes instead of Claude processes.
- [ ] **Step 4: Extract embedded pet data** into a pure-data asset module and keep animation selection deterministic.
- [ ] **Step 5: Run targeted tests and type checks** until clean.

### Task 4: Tkinter application and packaging

**Files:**
- Create: `codex_usage_widget/theme.py`
- Create: `codex_usage_widget/widgets.py`
- Create: `codex_usage_widget/app.py`
- Create: `codex_usage_widget/__init__.py`
- Create: `widget.pyw`
- Create: `실행.bat`
- Create: `pyproject.toml`
- Create: `README.md`
- Test: `tests/test_theme.py`
- Test: `tests/test_app_state.py`

**Interfaces:**
- Consumes: `UsageSnapshot`, `WidgetConfig`, Windows helpers, and assets.
- Produces: the visible full widget, mini mode, tray lifecycle, and background refresh service.

- [ ] **Step 1: Write failing pure UI-state tests** for gradient color, window label/detail formatting, stale/error footer text, and mini-row selection.
- [ ] **Step 2: Run targeted tests** and confirm expected failures.
- [ ] **Step 3: Implement tokenized theme and reusable Tk widgets** for usage rows, pet animation, slider, and mini batteries.
- [ ] **Step 4: Implement the app lifecycle** with worker refresh, `root.after` UI handoff, dynamic row creation/removal, menus, tray, drag, smart top-most, clean shutdown, and persistence.
- [ ] **Step 5: Add the minimal entry point, launcher, strict project configuration, and practical README.**
- [ ] **Step 6: Run `uv run ruff check .`, `uv run basedpyright`, and `uv run pytest -q`.**

### Task 5: Real integration and visual QA

**Files:**
- Create: `tests/manual/capture_widget.py`
- Create: `.artifacts/visual-qa/` screenshots and review notes

**Interfaces:**
- Consumes: current production build and real local Codex login.
- Produces: fresh full-light, full-dark, mini, transparency, and error-state evidence plus an independent verdict.

- [ ] **Step 1: Start the real widget** and compare displayed values with a fresh `account/rateLimits/read` result.
- [ ] **Step 2: Exercise full/mini, light/dark, transparency, tray restore, drag persistence, and Codex/other-app top-most switching.**
- [ ] **Step 3: Capture fresh native screenshots** for every enumerated state and verify PNG signatures, dimensions, Korean baselines, and compositing.
- [ ] **Step 4: Dispatch independent functional/design-system and visual/CJK reviewers** against the same captures and current source.
- [ ] **Step 5: Fix every blocking finding, recapture affected states, and repeat with fresh reviewers until PASS.**
- [ ] **Step 6: Re-run the complete test, lint, type, file-size, and real integration gates immediately before completion.**

