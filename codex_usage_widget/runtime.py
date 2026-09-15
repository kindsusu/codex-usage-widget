# pyright: reportAny=false, reportUnknownArgumentType=false, reportUnknownMemberType=false
"""Tk lifecycle and background-refresh orchestration."""

from __future__ import annotations

import tkinter as tk
from datetime import UTC, datetime
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
from typing import TYPE_CHECKING, Final, Literal, TypeAlias, final

from codex_usage_widget import actions, menus, updater, windows
from codex_usage_widget import config as widget_config
from codex_usage_widget.assets import PET_NAMES
from codex_usage_widget.config import TaskbarHost, TaskbarZone
from codex_usage_widget.fetcher import fetch_snapshot
from codex_usage_widget.opacity_popup import (
    OpacityPopupCallbacks,
    OpacityPopupController,
)
from codex_usage_widget.position_store import persist_window_position
from codex_usage_widget.presentation import present_snapshot
from codex_usage_widget.service import RefreshService
from codex_usage_widget.startup import report_startup_problem
from codex_usage_widget.taskbar import StripPlacement, TaskbarController
from codex_usage_widget.taskbar_details import TaskbarDetailsPopup, monitor_metrics
from codex_usage_widget.taskbar_model import build_taskbar_model
from codex_usage_widget.taskbar_native import taskbar_hosts
from codex_usage_widget.theme import theme_tokens
from codex_usage_widget.topmost import SmartTopmostController
from codex_usage_widget.tray import TrayCallbacks, TrayController
from codex_usage_widget.view import ViewActions, WidgetView
from codex_usage_widget.visibility_panel import VisibilityCallbacks, VisibilityPanel
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
    from codex_usage_widget.taskbar_placement import DropDecision

_INSTALL_ROOT: Final = Path(__file__).resolve().parent.parent
_CONFIG_PATH: Final = _INSTALL_ROOT / "widget_config.json"
_TASKBAR_RETRY_MS: Final = 10_000
_UPDATE_RETOGGLE_MS: Final = 3_000
SignalCommand: TypeAlias = Literal[
    "show",
    "exit",
    "details",
    "menu",
    "menu_close",
    "visibility_panel",
    "desktop",
    "desktop_normal",
    "desktop_hidden",
    "mini",
    "taskbar",
    "taskbar_drop",
    "refresh",
]
Signal: TypeAlias = tuple[SignalCommand, int, int]


def _strip_placement(
    config: WidgetConfig, *, claim_edge: bool = False
) -> StripPlacement:
    """Translate saved settings into the native worker's placement request."""
    return StripPlacement(
        zone=config.taskbar_zone,
        host=config.taskbar_host,
        monitor=config.taskbar_host_monitor,
        claim_edge=claim_edge,
    )


def _secondary_taskbar_exists() -> bool:
    """Whether Windows currently shows a taskbar on another monitor."""
    return any(not host.primary for host in taskbar_hosts())


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
        self._updates: Queue[str | None] = Queue()
        self._update_after_id: str | None = None
        self._update_busy = False
        self._taskbar_menu_open = Event()
        self._popup_suspensions: set[str] = set()
        self._drag_origin: tuple[int, int, int, int] | None = None
        self._closing = False
        self._tray = TrayController(
            lambda: self._queue("show"),
            lambda: self._queue("exit"),
            callbacks=TrayCallbacks(
                desktop_normal=lambda: self._queue("desktop_normal"),
                desktop_mini=lambda: self._queue("mini"),
                desktop_hidden=lambda: self._queue("desktop_hidden"),
                toggle_taskbar=lambda: self._queue("taskbar"),
                show_details=lambda: self._queue("details"),
                desktop_mode=lambda: actions.desktop_mode(self._config),
                taskbar_checked=lambda: self._config.taskbar_visible,
                refresh=lambda: self._queue("refresh"),
            ),
        )
        _ = self._tray.start()
        self._prepare_root()
        self._view = self._new_view()
        self._context_menu = menus.ContextMenuController(root)
        self._details = TaskbarDetailsPopup(root)
        self._opacity_popup = OpacityPopupController(
            root,
            OpacityPopupCallbacks(
                changed=self._set_opacity,
                opened=self._opacity_opened,
                closed=self._opacity_closed,
                context_requested=self._show_menu,
            ),
        )
        self._taskbar = TaskbarController(
            lambda x, y: self._signals.put(("details", x, y)),
            lambda x, y: self._signals.put(("visibility_panel", x, y)),
            self._queue_taskbar_menu,
            self._queue_taskbar_drop,
        )
        self._taskbar.set_placement(_strip_placement(self._config))
        self._drops: Queue[DropDecision] = Queue()
        self._visibility_panel = VisibilityPanel(
            root,
            VisibilityCallbacks(
                lambda: self._set_desktop_mode(actions.DesktopMode.NORMAL),
                lambda: self._set_desktop_mode(actions.DesktopMode.MINI),
                lambda: self._set_desktop_mode(actions.DesktopMode.HIDDEN),
                self._toggle_taskbar_visibility,
                self._visibility_trigger_contains,
            ),
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
        self._schedule_update_check(updater.FIRST_CHECK_MS)
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
            visibility=self._show_visibility_panel,
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
        if actions.desktop_mode(self._config) is not actions.DesktopMode.HIDDEN:
            self._set_desktop_mode(actions.DesktopMode.HIDDEN)

    def shutdown(self) -> None:
        """Stop adapters and ignore any worker result that arrives later."""
        if self._closing:
            return
        self._closing = True
        self._cancel_update_check()
        self._topmost.stop()
        self._service.shutdown()
        self._details.close()
        self._visibility_panel.close()
        self._opacity_popup.close()
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
        if self._drain_update_result():
            return
        while True:
            try:
                signal = self._signals.get_nowait()
            except Empty:
                break
            if self._handle_signal(signal) or self._closing:
                return
        self._apply_visibility()

    def _handle_signal(self, signal: Signal) -> bool:  # noqa: C901, PLR0912
        command, x, y = signal
        match command:
            case "show":
                if not self._config.desktop_visible:
                    self._set_desktop_mode(actions.DesktopMode.NORMAL)
                else:
                    self._apply_visibility(force=True)
            case "exit":
                self.shutdown()
                return True
            case "details":
                self._visibility_panel.close()
                self._opacity_popup.close()
                if x == 0 and y == 0:
                    x, y = self._root.winfo_pointerx(), self._root.winfo_pointery()
                self._details.toggle(x, y, self._service.state, self._config.theme)
            case "menu":
                self._show_menu(x, y)
            case "menu_close":
                _ = self._context_menu.dismiss()
            case "visibility_panel":
                self._show_visibility_panel(x, y)
            case "desktop":
                self._toggle_desktop_visibility()
            case "desktop_normal":
                self._set_desktop_mode(actions.DesktopMode.NORMAL)
            case "desktop_hidden":
                self._set_desktop_mode(actions.DesktopMode.HIDDEN)
            case "mini":
                self._toggle_mini()
            case "taskbar":
                self._toggle_taskbar_visibility()
            case "taskbar_drop":
                self._apply_taskbar_drop()
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
            if fallback_status is None and self._taskbar.host_fallback:
                # The chosen taskbar is gone (monitor unplugged); we borrow the
                # primary one and keep the saved setting for its return.
                fallback_status = "선택한 작업표시줄 없음 · 주 작업표시줄 사용 중"
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
        # force=True so a host that appeared or vanished refreshes the status
        # even when the effective visibility itself has not changed.
        self._apply_visibility(force=True)
        _ = self._root.after(_TASKBAR_RETRY_MS, self._retry_taskbar)

    def _schedule_update_check(self, delay_ms: int) -> None:
        """Arm the next release check, unless the user opted out."""
        self._cancel_update_check()
        if self._closing or not self._config.auto_update:
            return
        self._update_after_id = self._root.after(delay_ms, self._start_update_check)

    def _cancel_update_check(self) -> None:
        pending = self._update_after_id
        self._update_after_id = None
        if pending is not None:
            self._root.after_cancel(pending)

    def _start_update_check(self) -> None:
        self._update_after_id = None
        if self._closing or self._update_busy or not self._config.auto_update:
            return
        self._update_busy = True
        # Network, subprocess gates, and file moves all happen off the Tk
        # thread; the result comes back through the queue that _poll drains.
        Thread(target=self._run_update_check, daemon=True).start()

    def _run_update_check(self) -> None:
        self._updates.put(updater.try_update(root=_INSTALL_ROOT))

    def _drain_update_result(self) -> bool:
        """Apply one finished update attempt, reporting whether we are leaving."""
        try:
            tag = self._updates.get_nowait()
        except Empty:
            return False
        self._update_busy = False
        if tag is None:
            self._schedule_update_check(updater.INTERVAL_MS)
            return False
        self._restart_into_update()
        return True

    def _restart_into_update(self) -> None:
        """Hand over to a fresh process running the newly installed files."""
        widget_config.save_config(self._config_path, self._config)
        # Release the singleton BEFORE spawning: the replacement would
        # otherwise see this still-alive process and exit immediately.
        windows.release_single_instance()
        updater.relaunch(_INSTALL_ROOT)
        self.shutdown()

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
        _, dpi = monitor_metrics(self._root.winfo_x(), self._root.winfo_y())
        physical_scale = dpi / 96
        self._view.render(
            model,
            state,
            mini=self._config.mini_mode,
            factor=factor,
            physical_scale=physical_scale,
        )
        self._taskbar.update(build_taskbar_model(state, datetime.now(tz=UTC)))
        self._details.update(state, self._config.theme)
        self._visibility_panel.update(self._config)
        self._opacity_popup.update(self._config.opacity, self._config.theme)
        self._root.update_idletasks()
        width, height = self._view.pixel_size
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

    def _set_desktop_mode(self, mode: actions.DesktopMode) -> None:
        self._save_and_render(actions.set_desktop_mode(self._config, mode))

    def _toggle_desktop_visibility(self) -> None:
        self._save_and_render(actions.toggle_desktop_visibility(self._config))

    def _set_taskbar_placement(
        self,
        zone: TaskbarZone,
        host: TaskbarHost,
        monitor: str | None = None,
    ) -> None:
        """Persist a new strip destination and re-embed straight away."""
        resolved = monitor
        if resolved is None:
            resolved = (
                self._config.taskbar_host_monitor
                if host is TaskbarHost.SECONDARY
                else ""
            )
        config = actions.set_taskbar_placement(
            self._config, zone=zone, host=host, monitor=resolved
        )
        self._save_and_render(config)
        self._taskbar.set_placement(_strip_placement(config))

    def _queue_taskbar_drop(self, decision: DropDecision) -> None:
        """Hand a native drag result to the Tk thread."""
        self._drops.put(decision)
        self._signals.put(("taskbar_drop", 0, 0))

    def _apply_taskbar_drop(self) -> None:
        """Save where the user dropped the strip, then claim the slot."""
        try:
            decision = self._drops.get_nowait()
        except Empty:
            return
        host = (
            TaskbarHost.PRIMARY if decision.host.primary else TaskbarHost.SECONDARY
        )
        monitor = "" if decision.host.primary else decision.host.monitor
        config = actions.set_taskbar_placement(
            self._config, zone=decision.zone, host=host, monitor=monitor
        )
        self._save_and_render(config)
        self._taskbar.set_placement(
            _strip_placement(config, claim_edge=decision.claim_edge)
        )

    def _toggle_taskbar_visibility(self) -> None:
        self._save_and_render(actions.toggle_taskbar_visibility(self._config))

    def _show_opacity(self) -> None:
        _ = self._context_menu.dismiss()
        self._visibility_panel.close()
        self._details.close()
        avoid = (
            self._root.winfo_rootx(),
            self._root.winfo_rooty(),
            self._root.winfo_rootx() + self._root.winfo_width(),
            self._root.winfo_rooty() + self._root.winfo_height(),
        )
        self._opacity_popup.toggle(self._config.opacity, self._config.theme, avoid)

    def _set_opacity(self, opacity: float) -> None:
        self._save_and_render(actions.set_opacity(self._config, opacity))

    def _show_menu(self, x: int, y: int) -> None:
        self._visibility_panel.close()
        self._details.close()
        self._opacity_popup.close()
        callbacks = menus.MenuCallbacks(
            self.refresh,
            self._toggle_theme,
            self._show_opacity,
            lambda: self._set_desktop_mode(actions.DesktopMode.NORMAL),
            lambda: self._set_desktop_mode(actions.DesktopMode.MINI),
            lambda: self._set_desktop_mode(actions.DesktopMode.HIDDEN),
            self._toggle_taskbar_visibility,
            self._set_taskbar_placement,
            _secondary_taskbar_exists,
            self._toggle_topmost,
            self._toggle_auto_update,
            self.shutdown,
            self._set_scale,
            self._set_pet,
            self._menu_opened,
            self._menu_closed,
        )
        self._context_menu.toggle(x, y, self._config, callbacks)

    def _show_visibility_panel(self, x: int, y: int) -> None:
        _ = self._context_menu.dismiss()
        self._details.close()
        self._opacity_popup.close()
        brand = self._view.brand_screen_region
        avoid = None
        if brand is not None and brand.contains(x, y):
            avoid = (
                self._root.winfo_rootx(),
                self._root.winfo_rooty(),
                self._root.winfo_rootx() + self._root.winfo_width(),
                self._root.winfo_rooty() + self._root.winfo_height(),
            )
        self._visibility_panel.toggle(x, y, self._config, avoid=avoid)

    def _visibility_trigger_contains(self, x: int, y: int) -> bool:
        if self._taskbar.menu_button_contains_screen(x, y):
            return True
        brand = self._view.brand_screen_region
        return brand is not None and brand.contains(x, y)

    def _menu_opened(self) -> None:
        self._taskbar_menu_open.set()
        self._suspend_popup("menu")

    def _menu_closed(self) -> None:
        _ = self._taskbar.suppress_held_menu_release()
        self._taskbar_menu_open.clear()
        self._resume_popup("menu")

    def _opacity_opened(self) -> None:
        self._suspend_popup("opacity")

    def _opacity_closed(self) -> None:
        self._resume_popup("opacity")

    def _suspend_popup(self, owner: str) -> None:
        if not self._popup_suspensions:
            self._topmost.suspend()
        self._popup_suspensions.add(owner)

    def _resume_popup(self, owner: str) -> None:
        self._popup_suspensions.discard(owner)
        if not self._popup_suspensions and not self._closing:
            self._topmost.resume()

    def _set_scale(self, value: float, mini: bool) -> None:
        self._save_and_render(actions.set_scale(self._config, value, mini=mini))

    def _set_pet(self, name: str) -> None:
        self._save_and_render(actions.set_pet(self._config, name), rebuild=True)

    def _toggle_topmost(self) -> None:
        self._save_and_render(actions.toggle_smart_topmost(self._config))

    def _toggle_auto_update(self) -> None:
        self._save_and_render(actions.toggle_auto_update(self._config))
        self._schedule_update_check(_UPDATE_RETOGGLE_MS)

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
