# pyright: reportAny=false, reportUnknownArgumentType=false, reportUnknownMemberType=false
"""Tk lifecycle and background-refresh orchestration."""

from __future__ import annotations

import tkinter as tk
from datetime import UTC, datetime
from pathlib import Path
from queue import Empty, Queue
from threading import Event
from typing import TYPE_CHECKING, Final, Literal, TypeAlias, final

from codex_usage_widget import actions, menus, windows
from codex_usage_widget import config as widget_config
from codex_usage_widget.assets import PET_NAMES
from codex_usage_widget.fetcher import fetch_snapshot
from codex_usage_widget.position_store import persist_window_position
from codex_usage_widget.presentation import present_snapshot
from codex_usage_widget.service import RefreshService
from codex_usage_widget.startup import report_startup_problem
from codex_usage_widget.taskbar import TaskbarController
from codex_usage_widget.taskbar_details import TaskbarDetailsPopup
from codex_usage_widget.taskbar_model import build_taskbar_model
from codex_usage_widget.theme import theme_tokens
from codex_usage_widget.topmost import SmartTopmostController
from codex_usage_widget.tray import TrayCallbacks, TrayController
from codex_usage_widget.view import ViewActions, WidgetView
from codex_usage_widget.visibility_policy import (
    EffectiveVisibility,
    VisibilityFallback,
    resolve_visibility,
)
from codex_usage_widget.window_runtime import (
    format_window_position,
    resolve_initial_position,
)
from codex_usage_widget.window_surface import apply_window_surface
from codex_usage_widget.window_visibility import apply_native_window_state

if TYPE_CHECKING:
    from codex_usage_widget.config import WidgetConfig

_CONFIG_PATH: Final = Path(__file__).resolve().parent.parent / "widget_config.json"
_TASKBAR_RETRY_MS: Final = 10_000
SignalCommand: TypeAlias = Literal[
    "show",
    "exit",
    "details",
    "menu",
    "menu_close",
    "desktop",
    "mini",
    "taskbar",
    "refresh",
]
Signal: TypeAlias = tuple[SignalCommand, int, int]


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
        self._signals: Queue[Signal] = Queue()
        self._taskbar_menu_open = Event()
        self._drag_origin: tuple[int, int, int, int] | None = None
        self._closing = False
        self._tray = TrayController(
            lambda: self._queue("show"),
            lambda: self._queue("exit"),
            callbacks=TrayCallbacks(
                toggle_desktop=lambda: self._queue("desktop"),
                toggle_mini=lambda: self._queue("mini"),
                toggle_taskbar=lambda: self._queue("taskbar"),
                show_details=lambda: self._queue("details"),
                desktop_checked=lambda: self._config.desktop_visible,
                mini_checked=lambda: self._config.mini_mode,
                taskbar_checked=lambda: self._config.taskbar_visible,
                refresh=lambda: self._queue("refresh"),
            ),
        )
        _ = self._tray.start()
        self._prepare_root()
        self._view = self._new_view()
        self._context_menu = menus.ContextMenuController(root)
        self._details = TaskbarDetailsPopup(root)
        self._taskbar = TaskbarController(
            lambda x, y: self._signals.put(("details", x, y)),
            self._queue_taskbar_menu,
        )
        self._taskbar.set_visible(self._config.taskbar_visible)
        self._taskbar_requested: bool | None = self._config.taskbar_visible
        _ = self._taskbar.start()
        self._effective_visibility: EffectiveVisibility | None = None
        self._render()
        self._apply_visibility()
        apply_native_window_state(self._root, self._topmost.apply)
        _ = self._service.request_refresh()
        _ = root.after(100, self._poll)
        # Windows materializes the taskbar button a beat after the window maps,
        # so reassert the tool-window style once the shell has caught up.
        _ = root.after(200, self._reassert_no_taskbar)
        _ = root.after(self._config.refresh_seconds * 1000, self._periodic_refresh)
        _ = root.after(_TASKBAR_RETRY_MS, self._retry_taskbar)
        self._topmost.start()

    def _reassert_no_taskbar(self) -> None:
        if self._closing:
            return
        _ = windows.hide_from_taskbar(self._root.winfo_id())

    def _prepare_root(self) -> None:
        tokens = theme_tokens(self._config.theme)
        self._root.title("Codex Usage Widget")
        _ = self._root.overrideredirect(True)
        _ = self._root.configure(bg=tokens.surface_primary)
        _ = self._root.attributes("-alpha", self._config.opacity)
        self._root.update_idletasks()
        position = resolve_initial_position(self._config.position, self._root)
        _ = self._root.geometry(format_window_position(position.x, position.y))
        _ = self._root.bind("<ButtonPress-1>", self._drag_start)
        _ = self._root.bind("<B1-Motion>", self._drag_move)
        _ = self._root.bind("<ButtonRelease-1>", self._drag_end)
        _ = self._root.protocol("WM_DELETE_WINDOW", self.shutdown)

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
        """Persistently hide only the desktop surface."""
        if self._config.desktop_visible:
            self._toggle_desktop_visibility()

    def shutdown(self) -> None:
        """Stop adapters and ignore any worker result that arrives later."""
        if self._closing:
            return
        self._closing = True
        self._topmost.stop()
        self._service.shutdown()
        self._details.close()
        self._taskbar.stop()
        self._tray.stop()
        self._view.dispose()
        windows.release_single_instance()
        self._root.destroy()

    def _poll(self) -> None:
        if self._closing:
            return
        # Schedule before dispatch: tk_popup starts a nested modal Tk loop, so a
        # later taskbar click must still drain and unpost that active menu.
        _ = self._root.after(100, self._poll)
        if windows.consume_restore_request():
            self._signals.put(("show", 0, 0))
        if self._service.poll() is not None:
            self._render()
        while True:
            try:
                signal = self._signals.get_nowait()
            except Empty:
                break
            if self._handle_signal(signal) or self._closing:
                return
        self._apply_visibility()

    def _handle_signal(self, signal: Signal) -> bool:  # noqa: C901
        command, x, y = signal
        match command:
            case "show":
                if not self._config.desktop_visible:
                    self._toggle_desktop_visibility()
                else:
                    self._apply_visibility(force=True)
            case "exit":
                self.shutdown()
                return True
            case "details":
                if x == 0 and y == 0:
                    x, y = self._root.winfo_pointerx(), self._root.winfo_pointery()
                self._details.toggle(x, y, self._service.state, self._config.theme)
            case "menu":
                self._show_menu(x, y)
            case "menu_close":
                _ = self._context_menu.dismiss()
            case "desktop":
                self._toggle_desktop_visibility()
            case "mini":
                self._toggle_mini()
            case "taskbar":
                self._toggle_taskbar_visibility()
            case "refresh":
                self.refresh()
        return False

    def _queue(self, command: SignalCommand) -> None:
        self._signals.put((command, 0, 0))

    def _queue_taskbar_menu(self, x: int, y: int) -> None:
        """Snapshot popup state on native click to avoid close/reopen races."""
        command: SignalCommand = (
            "menu_close" if self._taskbar_menu_open.is_set() else "menu"
        )
        self._signals.put((command, x, y))

    def _apply_visibility(self, *, force: bool = False) -> None:
        effective = resolve_visibility(
            desktop_requested=self._config.desktop_visible,
            taskbar_requested=self._config.taskbar_visible,
            taskbar_attached=self._taskbar.attached,
            tray_available=self._tray.available,
        )
        requested = self._config.taskbar_visible
        if requested != getattr(self, "_taskbar_requested", None):
            # Keep the requested native surface active while Explorer attachment
            # is pending. Feeding effective visibility back here would prevent
            # the native worker from ever reattaching.
            self._taskbar.set_visible(requested)
            self._taskbar_requested = requested
        if force or effective != self._effective_visibility:
            fallback_status = {
                VisibilityFallback.TASKBAR_UNAVAILABLE: "작업표시줄 연결 대기 중",
                VisibilityFallback.NO_RESTORE_PATH: (
                    "트레이 복구를 위해 데스크톱 표시 중"
                ),
                None: None,
            }[effective.fallback]
            self._tray.set_status(fallback_status)
            if effective.desktop:
                self._root.deiconify()
                apply_native_window_state(self._root, self._topmost.apply)
            else:
                self._root.withdraw()
            self._effective_visibility = effective

    def _retry_taskbar(self) -> None:
        if self._closing:
            return
        if self._config.taskbar_visible and not self._taskbar.available:
            _ = self._taskbar.start()
        self._apply_visibility()
        _ = self._root.after(_TASKBAR_RETRY_MS, self._retry_taskbar)

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
        self._taskbar.update(build_taskbar_model(state, datetime.now(tz=UTC)))
        self._details.update(state, self._config.theme)
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
        # apply_window_surface churns -transparentcolor/-bg, which lets Windows
        # re-add the taskbar button; strip it again after every (re)layout.
        _ = windows.hide_from_taskbar(self._root.winfo_id())

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
        self._apply_visibility()
        self._tray.refresh_menu()

    def _toggle_theme(self) -> None:
        self._save_and_render(actions.toggle_theme(self._config), rebuild=True)

    def _toggle_mini(self) -> None:
        self._save_and_render(actions.toggle_mini_mode(self._config))

    def _toggle_desktop_visibility(self) -> None:
        self._save_and_render(actions.toggle_desktop_visibility(self._config))

    def _toggle_taskbar_visibility(self) -> None:
        self._save_and_render(actions.toggle_taskbar_visibility(self._config))

    def _show_opacity(self) -> None:
        menus.show_opacity_popup(self._root, self._config.opacity, self._set_opacity)

    def _set_opacity(self, opacity: float) -> None:
        self._save_and_render(actions.set_opacity(self._config, opacity))

    def _show_menu(self, x: int, y: int) -> None:
        callbacks = menus.MenuCallbacks(
            self.refresh,
            self._toggle_theme,
            self._toggle_mini,
            self._toggle_desktop_visibility,
            self._toggle_taskbar_visibility,
            self._toggle_topmost,
            self.hide,
            self.shutdown,
            self._set_scale,
            self._set_pet,
            self._menu_opened,
            self._menu_closed,
        )
        self._context_menu.toggle(x, y, self._config, callbacks)

    def _menu_opened(self) -> None:
        self._taskbar_menu_open.set()
        self._topmost.suspend()

    def _menu_closed(self) -> None:
        _ = self._taskbar.suppress_held_menu_release()
        self._taskbar_menu_open.clear()
        self._topmost.resume()

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


def run_widget() -> int:
    """Acquire the singleton and block in Tk's event loop."""
    _ = windows.enable_dpi_awareness()
    status = windows.acquire_single_instance_status()
    if status is windows.SingleInstanceStatus.ALREADY_RUNNING:
        if not windows.request_existing_instance_restore():
            report_startup_problem("already_running")
        return 0
    if status is windows.SingleInstanceStatus.UNAVAILABLE:
        report_startup_problem("single_instance_error")
        return 1
    try:
        _ = windows.create_restore_event()
        root = tk.Tk()
        _ = WidgetApplication(root)
        root.mainloop()
    finally:
        windows.release_single_instance()
    return 0
