# Codex Process-Aware Window Layering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the widget topmost whenever Codex is running, place it at the bottom application layer otherwise, and preserve tray-only taskbar behavior.

**Architecture:** Reuse the existing Toolhelp32 snapshot boundary to classify global Codex process presence. `SmartTopmostController` maps the existing smart-mode preference and live process state to the existing Win32 `top` or `bottom` z-order targets. Tray restoration reapplies the taskbar-hidden style before restoring process-aware layering.

**Tech Stack:** Python 3.12, Tkinter, ctypes Win32 APIs, pystray, pytest, Ruff, basedpyright.

## Global Constraints

- Do not add dependencies.
- Preserve the 750 ms polling interval and the existing single-instance mutex.
- Do not embed into Explorer `WorkerW` or add WMI permanent consumers.
- Keep each modified Python module at or below 250 nonblank, noncomment lines.
- Do not commit or push unless separately requested.

---

### Task 1: Process-Aware Window Layer

**Files:**
- Modify: `tests/test_windows.py`
- Modify: `tests/test_topmost.py`
- Modify: `codex_usage_widget/window_runtime.py`
- Modify: `codex_usage_widget/topmost.py`

**Interfaces:**
- Produces: `is_codex_running(records: tuple[ProcessRecord, ...]) -> bool`
- Produces: `read_codex_running() -> bool`
- Produces: `window_layer(smart_enabled: bool, codex_running: bool) -> Literal["top", "bottom"]`
- Consumes: `windows.set_window_zorder(hwnd, mode)`

- [x] **Step 1: Write failing process and layer tests**

Add tests proving direct Codex records match globally, Claude does not match, enabled/running maps to `top`, and absent or disabled maps to `bottom`. Update controller tests to inject `read_codex_running` and assert Boolean Tk topmost values plus Win32 layer calls.

```python
def test_codex_running_classifies_global_process_records() -> None:
    records = (
        ProcessRecord(pid=10, parent_pid=1, name="explorer.exe"),
        ProcessRecord(pid=20, parent_pid=1, name="Codex.exe"),
    )
    assert is_codex_running(records) is True


def test_window_layer_tracks_codex_process_presence() -> None:
    assert window_layer(True, True) == "top"
    assert window_layer(True, False) == "bottom"
    assert window_layer(False, True) == "bottom"
```

- [x] **Step 2: Run targeted tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_windows.py tests/test_topmost.py --basetemp=.artifacts/pytest-process-layer-red -p no:cacheprovider
```

Expected: collection failure because the new process and layer functions do not exist.

- [x] **Step 3: Implement minimal process detection and layer mapping**

In `window_runtime.py`, classify the existing immutable process rows and wrap native snapshot failure:

```python
def is_codex_running(records: tuple[ProcessRecord, ...]) -> bool:
    return any(_normalized_name(row.name) in _DIRECT_CODEX_NAMES for row in records)


def read_codex_running() -> bool:
    if os.name != "nt":
        return False
    try:
        return is_codex_running(_read_process_records())
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def window_layer(
    smart_enabled: bool,
    codex_running: bool,
) -> Literal["top", "bottom"]:
    return "top" if smart_enabled and codex_running else "bottom"
```

In `topmost.py`, replace foreground-window reading with `read_codex_running()`, map through `window_layer`, set the Tk topmost Boolean from the selected layer, and pass the same layer to `set_window_zorder`.

- [x] **Step 4: Run targeted tests and verify GREEN**

Run the Task 1 pytest command with `--basetemp=.artifacts/pytest-process-layer-green`.

Expected: all tests in `test_windows.py` and `test_topmost.py` pass.

---

### Task 2: Tray Restore and Taskbar-Hidden Style

**Files:**
- Modify: `tests/test_runtime.py`
- Modify: `codex_usage_widget/runtime.py`

**Interfaces:**
- Consumes: `windows.hide_from_taskbar(hwnd: int) -> bool`
- Consumes: `SmartTopmostController.apply() -> None`

- [x] **Step 1: Write a failing tray restoration test**

Create a minimal fake Tk root and partially constructed `WidgetApplication`. Queue a `show` signal and assert that one poll deiconifies the root, reapplies the taskbar-hidden style to the native handle, and reapplies process-aware layering.

```python
def test_tray_show_reapplies_taskbar_style_and_window_layer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application, root, topmost = _polling_application("show")
    hidden_handles: list[int] = []
    monkeypatch.setattr(
        "codex_usage_widget.runtime.windows.hide_from_taskbar",
        lambda hwnd: hidden_handles.append(hwnd) is None,
    )

    application._poll()

    assert root.deiconified == 1
    assert hidden_handles == [42]
    assert topmost.applied == 1
```

- [x] **Step 2: Run the runtime test and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_runtime.py --basetemp=.artifacts/pytest-tray-restore-red -p no:cacheprovider
```

Expected: the new assertions fail because the current `show` branch only deiconifies and lifts the window.

- [x] **Step 3: Implement taskbar style reapplication**

Replace the existing `lift()` call in the `show` branch with:

```python
_ = windows.hide_from_taskbar(self._root.winfo_id())
self._topmost.apply()
```

This keeps `runtime.py` at 250 pure lines.

- [x] **Step 4: Run the runtime test and verify GREEN**

Run the Task 2 pytest command with `--basetemp=.artifacts/pytest-tray-restore-green`.

Expected: all runtime tests pass.

---

### Task 3: Quality Gates and Real Windows QA

**Files:**
- Verify all changed Python and documentation files.

**Interfaces:**
- Consumes the startup shortcut and the real Tk/Win32 runtime.

- [x] **Step 1: Run static and automated verification**

```powershell
.\.venv\Scripts\python.exe -m ruff check codex_usage_widget tests
.\.venv\Scripts\python.exe -m basedpyright
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.artifacts/pytest-process-layer-final -p no:cacheprovider
```

Expected: Ruff and basedpyright exit 0; pytest reports all tests passing.

- [x] **Step 2: Run the no-excuse and size audits**

Run the programming-skill Python checker against changed Python paths, then measure pure LOC for every changed Python file. Expected: no rule violations and every production module is at most 250 lines.

- [x] **Step 3: Exercise the actual startup surface**

Restart the widget from `Codex Usage Widget.lnk`, wait for one responsive `Codex Usage Widget` window, inspect its extended taskbar styles, and confirm exactly one user-visible widget window and tray icon.

- [x] **Step 4: Verify both native z-order targets**

With the live Codex process, confirm controller state selects `top` and the widget remains above an ordinary test window. Exercise the real `bottom` Win32 target and confirm an ordinary test window covers the widget while the widget remains visible when the desktop is exposed. Restore the live process-aware state afterward.

- [x] **Step 5: Verify repository scope**

Run `git diff --check`, `git status -sb`, and `git diff --stat`. Expected: only the design, plan, targeted production files, and tests are changed; no QA artifacts remain.
