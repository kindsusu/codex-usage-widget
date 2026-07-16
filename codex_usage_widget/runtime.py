# pyright: reportAny=false, reportUnknownArgumentType=false, reportUnknownMemberType=false
"""Tk lifecycle and background-refresh orchestration."""

from __future__ import annotations

import tkinter as tk
from datetime import UTC, datetime
from pathlib import Path
from queue import Empty, Queue
from typing import TYPE_CHECKING, Final, Literal, final

from codex_usage_widget import actions, menus, windows
from codex_usage_widget import config as widget_config
from codex_usage_widget.assets import PET_NAMES
from codex_usage_widget.fetcher import fetch_snapshot
from codex_usage_widget.position_store import persist_window_position
from codex_usage_widget.presentation import present_snapshot
from codex_usage_widget.service import RefreshService
from codex_usage_widget.theme import theme_tokens
from codex_usage_widget.topmost import SmartTopmostController
from codex_usage_widget.tray import TrayController
from codex_usage_widget.view import ViewActions, WidgetView
from codex_usage_widget.window_runtime import (
    format_window_position,
    resolve_initial_position,
)
from codex_usage_widget.window_surface import apply_window_surface

if TYPE_CHECKING:
    from codex_usage_widget.config import WidgetConfig

_CONFIG_PATH: Final = Path(__file__).resolve().parent.parent / "widget_config.json"


@final
class WidgetApplication:
    """Coordinate Tk, refresh workers, persistence, and the optional tray."""

    def __init__(self, root: tk.Tk, config_path: Path = _CONFIG_PATH) -> None:
        """Build the native surface without starting Tk's main loop."""
        self._root = root
        self._config_path = config_path
        loaded = widget_config.load_config(config_path)
        self._config, config_changed = widget_config.select_initial_config(loaded)
        if config_changed:
            widget_config.save_config(config_path, self._config)
        self._topmost = SmartTopmostController(
            root,
            lambda: self._config.smart_topmost,
            lambda value: root.attributes("-topmost", value),
        )
        self._service = RefreshService(fetch_snapshot)
        self._signals: Queue[Literal["show", "exit"]] = Queue()
        self._drag_origin: tuple[int, int, int, int] | None = None
        self._closing = False
        self._tray = TrayController(
            lambda: self._signals.put("show"),
            lambda: self._signals.put("exit"),
        )
        _ = self._tray.start()
        self._prepare_root()
        self._view = self._new_view()
        self._render()
        _ = self._service.request_refresh()
        _ = root.after(100, self._poll)
        _ = root.after(self._config.refresh_seconds * 1000, self._periodic_refresh)
        self._topmost.start()

    def _prepare_root(self) -> None:
        tokens = theme_tokens(self._config.theme)
        self._root.title("Codex Usage Widget")
        _ = self._root.overrideredirect(True)
        _ = self._root.configure(bg=tokens.surface_primary)
        _ = self._root.attributes("-alpha", self._config.opacity)
        self._root.update_idletasks()
        position = resolve_initial_position(self._config.position, self._root)
        _ = self._root.geometry(format_window_position(position.x, position.y))
        _ = self._root.bind("<Control-r>", self._refresh_event)
        _ = self._root.bind("<Control-m>", self._mini_event)
        _ = self._root.bind("<Control-t>", self._theme_event)
        _ = self._root.bind("<Escape>", self._hide_event)
        _ = self._root.bind("<ButtonPress-1>", self._drag_start)
        _ = self._root.bind("<B1-Motion>", self._drag_move)
        _ = self._root.bind("<ButtonRelease-1>", self._drag_end)
        _ = self._root.protocol("WM_DELETE_WINDOW", self.shutdown)
        _ = windows.hide_from_taskbar(self._root.winfo_id())
        self._topmost.apply()

    def _new_view(self) -> WidgetView:
        actions = ViewActions(
            theme=self._toggle_theme,
            opacity=self._show_opacity,
            mini=self._toggle_mini,
            hide=self.hide,
            refresh=self.refresh,
            menu=self._show_menu,
        )
        return WidgetView(
            self._root,
            actions,
            self._config.pet or PET_NAMES[0],
            theme_tokens(self._config.theme),
        )

    def refresh(self) -> None:
        """Request a coalesced background refresh and redraw its state."""
        _ = self._service.request_refresh()
        self._render()

    def hide(self) -> None:
        """Hide without terminating so the tray can restore the widget."""
        if self._tray.available:
            self._root.withdraw()
            return
        self.shutdown()

    def shutdown(self) -> None:
        """Stop adapters and ignore any worker result that arrives later."""
        if self._closing:
            return
        self._closing = True
        self._topmost.stop()
        self._service.shutdown()
        self._tray.stop()
        self._view.dispose()
        windows.release_single_instance()
        self._root.destroy()

    def _poll(self) -> None:
        if self._closing:
            return
        if self._service.poll() is not None:
            self._render()
        try:
            signal = self._signals.get_nowait()
        except Empty:
            signal = None
        match signal:  # noqa: RUF100  # noqa: MATCH_OK
            case "show":
                self._root.deiconify()
                self._root.lift()
            case "exit":
                self.shutdown()
                return
            case None:
                pass
        if not self._tray.available and self._root.state() == "withdrawn":
            self._root.deiconify()
        _ = self._root.after(100, self._poll)

    def _periodic_refresh(self) -> None:
        if self._closing:
            return
        self.refresh()
        _ = self._root.after(
            self._config.refresh_seconds * 1000,
            self._periodic_refresh,
        )

    def _render(self) -> None:
        state = self._service.state
        model = (
            None
            if state.snapshot is None
            else present_snapshot(state.snapshot, datetime.now(tz=UTC))
        )
        factor = (
            self._config.mini_scale if self._config.mini_mode else self._config.scale
        )
        _ = self._root.tk.call("tk", "scaling", 4.0 / 3.0 * factor)
        tokens = theme_tokens(self._config.theme)
        apply_window_surface(self._root, tokens, mini=self._config.mini_mode)
        self._view.render(model, state, mini=self._config.mini_mode)
        self._root.update_idletasks()
        width = round(
            (tokens.mini_width if self._config.mini_mode else tokens.full_width)
            * factor
        )
        height = round(
            (
                tokens.mini_height
                if self._config.mini_mode
                else self._root.winfo_reqheight()
            )
            * factor
        )
        _ = self._root.geometry(f"{width}x{height}")

    def _save_and_render(self, config: WidgetConfig, *, rebuild: bool = False) -> None:
        self._config = config
        widget_config.save_config(self._config_path, config)
        _ = self._root.attributes("-alpha", config.opacity)
        if rebuild:
            _ = self._root.configure(bg=theme_tokens(config.theme).surface_primary)
            self._view.dispose()
            self._view = self._new_view()
        self._topmost.apply()
        self._render()

    def _toggle_theme(self) -> None:
        self._save_and_render(actions.toggle_theme(self._config), rebuild=True)

    def _toggle_mini(self) -> None:
        self._save_and_render(actions.toggle_mini_mode(self._config))

    def _show_opacity(self) -> None:
        menus.show_opacity_popup(self._root, self._config.opacity, self._set_opacity)

    def _set_opacity(self, opacity: float) -> None:
        self._save_and_render(actions.set_opacity(self._config, opacity))

    def _show_menu(self, x: int, y: int) -> None:
        callbacks = menus.MenuCallbacks(
            self.refresh,
            self._toggle_theme,
            self._toggle_mini,
            self._toggle_topmost,
            self.hide,
            self.shutdown,
            self._set_scale,
            self._set_pet,
            self._topmost.suspend,
            self._topmost.resume,
        )
        menus.show_context_menu(self._root, x, y, self._config, callbacks)

    def _set_scale(self, value: float, mini: bool) -> None:
        self._save_and_render(actions.set_scale(self._config, value, mini=mini))

    def _set_pet(self, name: str) -> None:
        self._save_and_render(actions.set_pet(self._config, name), rebuild=True)

    def _toggle_topmost(self) -> None:
        self._save_and_render(actions.toggle_smart_topmost(self._config))

    def _drag_start(self, event: tk.Event[tk.Misc]) -> None:
        self._drag_origin = (
            event.x_root,
            event.y_root,
            self._root.winfo_x(),
            self._root.winfo_y(),
        )

    def _drag_move(self, event: tk.Event[tk.Misc]) -> None:
        if self._drag_origin is None:
            return
        pointer_x, pointer_y, origin_x, origin_y = self._drag_origin
        x = origin_x + event.x_root - pointer_x
        y = origin_y + event.y_root - pointer_y
        _ = self._root.geometry(format_window_position(x, y))

    def _drag_end(self, _event: tk.Event[tk.Misc]) -> None:
        self._drag_origin = None
        self._config = persist_window_position(
            self._config_path,
            self._config,
            windows.WindowPosition(self._root.winfo_x(), self._root.winfo_y()),
        )

    def _refresh_event(self, _event: tk.Event[tk.Misc]) -> None:
        self.refresh()

    def _mini_event(self, _event: tk.Event[tk.Misc]) -> None:
        self._toggle_mini()

    def _theme_event(self, _event: tk.Event[tk.Misc]) -> None:
        self._toggle_theme()

    def _hide_event(self, _event: tk.Event[tk.Misc]) -> None:
        self.hide()


def run_widget() -> int:
    """Acquire the singleton and block in Tk's event loop."""
    _ = windows.enable_dpi_awareness()
    if not windows.acquire_single_instance():
        return 0
    try:
        root = tk.Tk()
        _ = WidgetApplication(root)
        root.mainloop()
    finally:
        windows.release_single_instance()
    return 0
