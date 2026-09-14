"""Import-and-smoke gate shared by the release workflow and the auto-updater.

Reaching a zero exit code proves that every module-level statement in the
package executed in a fresh interpreter and that the core pure functions still
answer the way the test suite expects. It opens no window, holds no singleton,
and never reads or writes ``widget_config.json``.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path
from typing import final

import codex_usage_widget
from codex_usage_widget import updater
from codex_usage_widget.actions import toggle_mini_mode, toggle_theme
from codex_usage_widget.assets import PET_NAMES
from codex_usage_widget.config import ThemeName, WidgetConfig, load_config
from codex_usage_widget.theme import theme_tokens


@final
class SelftestError(Exception):
    """One named smoke check did not hold."""

    def __init__(self, check: str) -> None:
        """Name only the failed check so no runtime value can leak."""
        self.check = check
        super().__init__(f"selftest check failed: {check}")


def run_selftest() -> int:
    """Import every module, smoke-check pure logic, and return an exit code."""
    try:
        _ = import_all_modules()
        smoke_check()
    except Exception as error:  # noqa: BLE001 -- the gate reports, never crashes
        _ = sys.stderr.write(f"selftest failed: {type(error).__name__}: {error}\n")
        return 1
    return 0


def import_all_modules() -> tuple[str, ...]:
    """Import every module in the package and return their names."""
    names = tuple(
        f"{codex_usage_widget.__name__}.{info.name}"
        for info in pkgutil.iter_modules(codex_usage_widget.__path__)
    )
    for name in names:
        _ = importlib.import_module(name)
    return names


def smoke_check() -> None:
    """Assert the load-bearing pure behaviour the widget is built on."""
    defaults = WidgetConfig()
    _require(bool(PET_NAMES), "pets are available")
    _require(
        load_config(Path("nonexistent-widget-config.json")) == defaults,
        "missing config falls back to defaults",
    )
    _require(
        toggle_theme(defaults).theme is ThemeName.DARK,
        "theme toggles away from light",
    )
    _require(
        toggle_mini_mode(WidgetConfig(desktop_visible=False)).desktop_visible,
        "mini mode reveals the desktop surface",
    )
    _require(
        theme_tokens(ThemeName.DARK) != theme_tokens(ThemeName.LIGHT),
        "themes render distinct palettes",
    )
    _require(defaults.auto_update, "auto update is on by default")
    _require(
        updater.is_newer("v9.0.0", codex_usage_widget.__version__)
        and not updater.is_newer("v0.0.1", codex_usage_widget.__version__)
        and not updater.is_newer("latest", codex_usage_widget.__version__),
        "only a strictly newer numeric tag is an update",
    )
    _require(
        updater.digest_matches(b"codex", _digest_line(b"codex"))
        and not updater.digest_matches(b"codex", _digest_line(b"tampered")),
        "release digests are verified",
    )


def _digest_line(payload: bytes) -> str:
    import hashlib  # noqa: PLC0415 -- only the gate needs it

    return f"{hashlib.sha256(payload).hexdigest()}  {updater.ASSET_NAME}"


def _require(condition: bool, check: str) -> None:
    if not condition:
        raise SelftestError(check)
