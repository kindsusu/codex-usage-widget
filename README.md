# Codex Usage Widget

📖 [한국어 사용설명서 (Korean user manual)](docs/사용설명서.md)

A small always-on-desktop Windows widget that shows your current Codex usage limits. It only displays the rate-limit windows Codex actually returns — no guessing of names or ordering. If your account has only a weekly limit, you see one row; if it also has a 5-hour limit, both rows appear.

![desktop card, dark theme](docs/img/desktop-card-dark.png)

## Requirements

- Windows 10/11
- Python 3.11+
- Codex desktop app or Codex CLI installed
- Signed in to Codex with your ChatGPT account

## Install & Run

Open the project folder in PowerShell and run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Then double-click `실행.bat`, or run directly:

```powershell
.\.venv\Scripts\pythonw.exe widget.pyw
```

## Usage

The desktop card and display panel follow the approved redesign. See the [Windows verification results](docs/desktop-redesign-validation.md) for tested interactions and rendering limits.

- **Desktop card**: a Codex logo, plan, and remaining-usage bars in full mode; mini mode uses a 244×46 compact strip. The saved pet preference remains available but is not shown on this card design.
- **Taskbar indicator**: an embedded, compact two-row view of the remaining percentage for the usage windows Codex actually returns. Its per-pixel-alpha surface lets the Windows taskbar material show through; hover adds a soft translucent background. Left-click on usage toggles a non-modal detail popup. Left-clicking the Codex button opens the three-checkbox display panel; right-clicking opens the advanced native menu, where you choose refresh, theme, opacity, scale, or exit.
- **Independent surfaces**: desktop visibility, desktop mini mode, and taskbar visibility are saved independently. The four visibility states are both shown, desktop only, taskbar only, and both hidden (restorable from the tray).
- **Moving the widget**: drag any empty area; the position is saved.
- **Smart position switching**: when ON, the widget floats above other windows only while the widget itself or Codex (a terminal or the ChatGPT app) is in the foreground. When OFF, the widget stays always on top.

Each progress bar represents remaining capacity. Its theme-aware green, amber, or red state is paired with the exact percentage, so the value does not depend on color alone. The taskbar detail popup shows the reset time for each returned usage window and its current update, stale-data, or error status.

## Auto-update

The widget keeps itself current without any action from you:

1. 20 s after launch, and every 12 h after that, it resolves `…/releases/latest` and compares the tag with its own `__version__` (a redirect on github.com, not an API call, so there is no rate limit to hit).
2. If the tag is strictly newer, it downloads `codex-usage-widget.zip` and `codex-usage-widget.zip.sha256` from that release.
3. Three gates must all pass before anything on disk changes: the sha256 matches, every staged `.py`/`.pyw` compiles, and a separate interpreter runs `widget.pyw --selftest` against the staged tree and exits 0.
4. The current `codex_usage_widget/`, `widget.pyw`, `assets/`, `pyproject.toml`, `실행.bat`, and `THIRD_PARTY_NOTICES.md` move into `.update-backup\`, the staged copies take their place, and `.venv\Scripts\python.exe -m pip install -e . --quiet` re-resolves dependencies. If any of that fails, the backup is moved straight back.
5. The widget then restarts itself — you see it blink once.

`widget_config.json` and `.venv\` are never inside the replaced set, so settings and the virtual environment survive every update. Every step is written to `update.log` beside the script (tags and failure categories only — no paths, no tokens). Turn it off with **자동 업데이트** in the right-click menu (`"auto_update": false` in `widget_config.json`); the running version is shown at the bottom of that same menu. To roll back by hand, exit the widget and copy `.update-backup\` back over the folder.

Only published Releases reach users; commits to `main` do not.

### Publishing a release (maintainer)

```bash
# 1. bump the version in BOTH pyproject.toml and codex_usage_widget/__init__.py
# 2. tag — the tag must equal both or the workflow refuses
git tag v0.3.0
git push --tags
```

[`release.yml`](.github/workflows/release.yml) checks that the tag, `pyproject.toml`, and `__init__.py` agree, runs the full `pytest` suite plus `py_compile` and `--selftest`, builds the zip and its sha256, and creates the Release with both assets. Users pick it up within 12 h (or on their next launch).

## Troubleshooting

- **Codex not found**: install the Codex desktop app or CLI, then relaunch. If it is installed in an unusual location, set the `CODEX_EXE` environment variable to the full path of `codex.exe`.
- **Login required**: complete the ChatGPT sign-in in the Codex desktop app or CLI, then refresh the widget.
- **No tray icon**: some environments have no usable system tray. The widget itself and the right-click quit menu keep working.
- **Nothing happens when starting**: an older widget instance can block this version through the global single-instance guard. Exit the older instance from its tray menu, then start this version again. In this version, rerunning `실행.bat` restores the existing instance's desktop; startup errors show guidance and record only an error category in `%LOCALAPPDATA%\CodexUsageWidget\startup.log`.
- **Fewer usage rows than expected**: the widget never fabricates 5-hour/weekly windows the server did not return.
- **Taskbar indicator unavailable**: the indicator targets the primary horizontal Windows 11 taskbar. It prefers space before the notification area, then uses verified space left of Start while protecting the leftmost 200 logical pixels reserved for system controls. If no 197-pixel space is available, or for vertical/unsupported taskbars, secondary-monitor taskbars, or Explorer transitions, it falls back to the desktop widget temporarily without changing saved visibility settings. Windows 10 has not been tested on a live device.

## Privacy

The widget asks the local official Codex `app-server` process for `account/rateLimits/read` only. It never reads or modifies `auth.json` directly, and it never stores, logs, or displays OAuth tokens, e-mail addresses, user IDs, or account IDs. The config file holds display settings only (theme, transparency, scale, position, pet, and desktop/taskbar visibility). The retained pet preference is not rendered by the current desktop card.

## License & Assets

Pet assets are shared with the same author's MIT project [kindsusu/claude-usage-widget](https://github.com/kindsusu/claude-usage-widget). The bundled assets serve the desktop card, mini strip, taskbar indicator, and tray. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the applicable notices.
