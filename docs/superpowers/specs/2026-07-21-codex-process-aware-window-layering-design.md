# Codex Process-Aware Window Layering Design

## Goal

Make the widget follow the Codex process lifecycle instead of the foreground-window lifecycle:

- While any supported Codex process is running, keep the widget above ordinary application windows.
- While Codex is not running, keep the widget visible at the bottom of the ordinary top-level window stack, above the desktop but below other applications.
- Never expose the widget as a taskbar button; keep the system-tray icon as the persistent management surface.

## Current Behavior

`SmartTopmostController` polls the foreground process every 750 ms. It raises the widget when either the widget has focus or Codex owns the foreground. Otherwise it only removes topmost status and returns the window to the normal application layer.

The runtime already starts a tray controller and applies the Win32 tool-window extended style, but the taskbar style is applied only during initial root preparation.

## Selected Architecture

### Process detection

Reuse the existing Toolhelp32 process snapshot boundary in `window_runtime.py`. Add a pure classifier that accepts immutable `ProcessRecord` values and reports whether a supported Codex executable exists anywhere in the table. The native reader wraps snapshot failures and returns `False` rather than terminating the Tk polling loop.

Supported direct names remain centralized in the existing Codex executable-name set. Claude and unrelated terminal processes must not match.

### Window-layer state

Replace the foreground-sensitive decision with a process-aware layer decision:

| Smart mode | Codex running | Layer |
|---|---:|---|
| enabled | yes | topmost (`HWND_TOPMOST`) |
| enabled | no | desktop-level bottom (`HWND_BOTTOM`) |
| disabled | either | desktop-level bottom (`HWND_BOTTOM`) |

Widget focus does not override the process state. This prevents the widget from remaining above unrelated applications after Codex exits.

The existing context-menu suspension remains: while a popup owns the grab, polling does not reorder the parent. On resume, the controller immediately reapplies the process-derived layer.

### Taskbar and tray behavior

Keep `WS_EX_TOOLWINDOW` and clear `WS_EX_APPWINDOW`. Reapply the style after the native Tk window is materialized and whenever the root is restored from the tray, because Tk can recreate or restyle the wrapper window during deiconify operations.

The tray remains available for open and exit actions. Hiding withdraws the root without terminating the widget. If the optional tray backend cannot start, hiding continues to terminate the app so the user is not left with an unreachable background process.

## Data Flow

1. `SmartTopmostController` polls every 750 ms.
2. The process reader snapshots running processes and returns a Boolean Codex state.
3. The controller maps the state and the existing smart-mode preference to `top` or `bottom`.
4. The Tk topmost attribute and Win32 z-order are updated without moving or activating the window.
5. Tray restore deiconifies the root, reapplies the taskbar-hidden style, and immediately reapplies the current process-derived layer.

## Error Handling

- Win32 snapshot or z-order failures are contained and retried on the next polling interval.
- A missing Codex process is a normal `False` state, not an error.
- Taskbar-style failures do not disable the tray or crash the UI.
- The single-instance mutex remains unchanged.

## Test Strategy

### Automated

- Pure process classifier: direct Codex names match; Claude and unrelated names do not.
- Layer decision: Codex running maps to top; absent or smart mode disabled maps to bottom.
- Controller: polling applies `top` and `bottom`, preserves menu suspension, and cancels its timer.
- Runtime: initial preparation and tray restoration reapply taskbar-hidden styling.
- Full pytest, Ruff, and basedpyright verification.

### Manual Windows QA

- With the real Codex process running, observe one responsive widget window with topmost extended style and top z-order behavior.
- Exercise the bottom-layer Win32 path and confirm an ordinary application covers the widget while the widget remains visible when the desktop is exposed.
- Confirm no taskbar button is present and exactly one Codex tray icon exists.
- Launch the startup shortcut a second time and confirm the singleton prevents a duplicate widget window.

## Out of Scope

- Embedding the widget into Explorer's undocumented `WorkerW` desktop host.
- WMI permanent event consumers or administrator-only scheduled tasks.
- Changing visual layout, usage calculations, refresh cadence, or asset design.
