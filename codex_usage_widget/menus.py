# pyright: reportAny=false, reportUnknownArgumentType=false, reportUnknownMemberType=false
"""Native popup menus and opacity controls for the compact widget."""

from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from codex_usage_widget.assets import PET_NAMES
from codex_usage_widget.config import ThemeName, WidgetConfig
from codex_usage_widget.theme import ThemeTokens, theme_tokens

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True, slots=True)
class MenuCallbacks:
    """Behavior supplied by the application controller."""

    refresh: Callable[[], None]
    theme: Callable[[], None]
    mini: Callable[[], None]
    desktop_visibility: Callable[[], None]
    taskbar_visibility: Callable[[], None]
    topmost: Callable[[], None]
    hide: Callable[[], None]
    exit_app: Callable[[], None]
    scale: Callable[[float, bool], None]
    pet: Callable[[str], None]
    menu_opened: Callable[[], None]
    menu_closed: Callable[[], None]


def show_context_menu(
    root: tk.Tk,
    x: int,
    y: int,
    config: WidgetConfig,
    callbacks: MenuCallbacks,
) -> None:
    """Show the complete mouse-driven settings menu."""
    ContextMenuController(root).toggle(x, y, config, callbacks)


@final
class ContextMenuController:
    """Own one popup so a repeated trigger can dismiss its modal loop."""

    def __init__(self, root: tk.Tk) -> None:
        """Bind the Tk owner without creating a menu yet."""
        self._root = root
        self._active: tk.Menu | None = None
        self._native_owner = 0

    @property
    def active(self) -> bool:
        """Return whether this controller currently owns a posted menu."""
        return self._active is not None

    def dismiss(self) -> bool:
        """Unpost the active menu, returning whether one was open."""
        menu = self._active
        if menu is None:
            return False
        _cancel_native_popup(self._native_owner)
        menu.unpost()
        return True

    def toggle(
        self,
        x: int,
        y: int,
        config: WidgetConfig,
        callbacks: MenuCallbacks,
    ) -> None:
        """Dismiss the posted menu or show a newly rebuilt one."""
        if self.dismiss():
            return
        self._show(x, y, config, callbacks)

    def _show(
        self,
        x: int,
        y: int,
        config: WidgetConfig,
        callbacks: MenuCallbacks,
    ) -> None:
        root = self._root
        tokens = theme_tokens(config.theme)
        menu = _new_menu(root, tokens)
        self._active = menu
        native_owner = 0
        menu_variables: tuple[tk.BooleanVar, ...] = ()
        try:
            # Tcl does not retain Python Variable objects. Keep these references
            # alive for the full modal loop so every check mark remains visible.
            menu_variables = _populate_context_menu(menu, config, callbacks, tokens)
            callbacks.menu_opened()
            native_owner = _prepare_native_popup(root)
            self._native_owner = native_owner
            menu.tk_popup(x, y)
        finally:
            _finish_native_popup(native_owner)
            self._native_owner = 0
            self._active = None
            with suppress(tk.TclError):
                callbacks.menu_closed()

            def destroy_menu() -> None:
                with suppress(tk.TclError):
                    menu.destroy()
                _ = menu_variables

            # Windows can return from TrackPopupMenu before Tk dispatches the
            # selected row's Tcl command. Destroying here deletes that command,
            # so defer disposal until the pending selection has run.
            try:
                _ = root.after_idle(destroy_menu)
            except tk.TclError:
                destroy_menu()


def _populate_context_menu(
    menu: tk.Menu,
    config: WidgetConfig,
    callbacks: MenuCallbacks,
    tokens: ThemeTokens,
) -> tuple[tk.BooleanVar, ...]:
    """Populate one rebuilt context menu from current configuration."""
    # Rebuilt on every popup, so each variable snapshots the CURRENT config.
    # These BooleanVars MUST stay referenced: an unreferenced tk.BooleanVar is
    # garbage-collected immediately, which unsets its Tcl variable and makes the
    # checkbutton render unchecked. Named locals stay alive across the modal
    # tk_popup below, so the checkbuttons reflect live state while displayed.
    theme_on = tk.BooleanVar(menu, value=config.theme is ThemeName.DARK)
    mini_on = tk.BooleanVar(menu, value=config.mini_mode)
    desktop_on = tk.BooleanVar(menu, value=config.desktop_visible)
    taskbar_on = tk.BooleanVar(menu, value=config.taskbar_visible)
    topmost_on = tk.BooleanVar(menu, value=config.smart_topmost)
    _ = menu.add_command(label="새로고침", command=callbacks.refresh)
    _ = menu.add_checkbutton(
        label="다크/라이트 전환",
        command=callbacks.theme,
        variable=theme_on,
    )
    _ = menu.add_checkbutton(
        label="데스크톱 표시",
        command=callbacks.desktop_visibility,
        variable=desktop_on,
    )
    _ = menu.add_checkbutton(
        label="미니모드",
        command=callbacks.mini,
        variable=mini_on,
    )
    _ = menu.add_checkbutton(
        label="작업표시줄 표시",
        command=callbacks.taskbar_visibility,
        variable=taskbar_on,
    )
    _ = menu.add_checkbutton(
        label="스마트 포지션 스위칭",
        command=callbacks.topmost,
        variable=topmost_on,
    )
    _add_scale_menu(menu, "전체 배율", False, callbacks.scale)
    _add_scale_menu(menu, "미니 배율", True, callbacks.scale)
    pet_menu = _new_menu(menu, tokens)
    for name in PET_NAMES:
        _ = pet_menu.add_command(label=name, command=_pet_command(callbacks.pet, name))
    _ = menu.add_cascade(label="펫 선택", menu=pet_menu)
    _ = menu.add_separator()
    _ = menu.add_command(label="데스크톱 숨기기", command=callbacks.hide)
    _ = menu.add_command(label="종료", command=callbacks.exit_app)
    return theme_on, mini_on, desktop_on, taskbar_on, topmost_on


def show_opacity_popup(
    root: tk.Tk,
    opacity: float,
    callback: Callable[[float], None],
    tokens: ThemeTokens | None = None,
) -> None:
    """Show a compact token-styled 30-100 percent opacity slider."""
    resolved = tokens or _tokens_from_root(root)
    popup = tk.Toplevel(root)
    _ = popup.overrideredirect(True)
    _ = popup.attributes("-topmost", True)
    _ = popup.resizable(False, False)
    _ = popup.configure(bg=resolved.surface_primary)
    _ = popup.geometry(f"196x76+{root.winfo_x() + 52}+{root.winfo_y() + 34}")
    shell = tk.Frame(
        popup,
        bg=resolved.surface_primary,
        highlightbackground=resolved.bar_background,
        highlightthickness=1,
        padx=resolved.space_5,
        pady=resolved.space_3,
    )
    _ = shell.pack(fill="both", expand=True)
    header = tk.Frame(shell, bg=resolved.surface_primary)
    _ = header.pack(fill="x")
    _ = tk.Label(
        header,
        text="투명도",
        bg=resolved.surface_primary,
        fg=resolved.text_primary,
        font=(resolved.font_family, 9, "bold"),
    ).pack(side="left")
    value_label = tk.Label(
        header,
        bg=resolved.surface_primary,
        fg=resolved.text_secondary,
        font=(resolved.font_family, 8),
    )
    _ = value_label.pack(side="right")
    track_width = 152
    slider = tk.Canvas(
        shell,
        width=track_width,
        height=28,
        bg=resolved.surface_primary,
        highlightthickness=0,
        cursor="hand2",
    )
    _ = slider.pack(fill="x", pady=(resolved.space_2, 0))

    current = max(0.3, min(1.0, opacity))

    def draw(value: float) -> None:
        _ = slider.delete("all")
        left, right, center = 6, track_width - 6, 14
        fraction = (value - 0.3) / 0.7
        thumb_x = left + fraction * (right - left)
        _ = slider.create_line(
            left, center, right, center, fill=resolved.bar_background, width=4
        )
        _ = slider.create_line(
            left, center, thumb_x, center, fill=resolved.accent_primary, width=4
        )
        _ = slider.create_oval(
            thumb_x - 5,
            center - 5,
            thumb_x + 5,
            center + 5,
            fill=resolved.surface_primary,
            outline=resolved.focus_ring,
            width=2,
        )
        _ = value_label.configure(text=f"{round(value * 100)}%")

    def changed(event: tk.Event[tk.Misc]) -> None:
        value = opacity_from_position(event.x - 6, track_width - 12)
        draw(value)
        callback(value)

    _ = slider.bind("<Button-1>", changed)
    _ = slider.bind("<B1-Motion>", changed)
    _ = popup.bind("<Escape>", lambda _event: popup.destroy())
    draw(current)
    _ = popup.focus_force()


def opacity_from_position(position: int, track_width: int) -> float:
    """Map a slider coordinate to the supported opacity range."""
    fraction = max(0.0, min(1.0, position / track_width))
    return round(0.3 + fraction * 0.7, 3)


def _add_scale_menu(
    menu: tk.Menu,
    label: str,
    mini: bool,
    callback: Callable[[float, bool], None],
) -> None:
    submenu = tk.Menu(menu, tearoff=False)
    for value in (0.75, 1.0, 1.3, 1.5, 2.0):
        _ = submenu.add_command(
            label=f"{round(value * 100)}%",
            command=_scale_command(callback, value, mini),
        )
    _ = menu.add_cascade(label=label, menu=submenu)


def _scale_command(
    callback: Callable[[float, bool], None],
    value: float,
    mini: bool,
) -> Callable[[], None]:
    return lambda: callback(value, mini)


def _pet_command(
    callback: Callable[[str], None],
    name: str,
) -> Callable[[], None]:
    return lambda: callback(name)


def _new_menu(parent: tk.Misc, tokens: ThemeTokens) -> tk.Menu:
    return tk.Menu(
        parent,
        tearoff=False,
        bg=tokens.surface_primary,
        fg=tokens.text_primary,
        activebackground=tokens.control_surface_hover,
        activeforeground=tokens.control_hover,
        selectcolor=tokens.accent_primary,
        borderwidth=1,
        relief="flat",
        font=(tokens.font_family, 9),
    )


def _tokens_from_root(root: tk.Tk) -> ThemeTokens:
    dark = theme_tokens(ThemeName.DARK)
    theme = (
        ThemeName.DARK
        if str(root.cget("bg")) == dark.surface_primary
        else ThemeName.LIGHT
    )
    return theme_tokens(theme)


def _prepare_native_popup(root: tk.Tk) -> int:
    """Make the owner foreground so Windows dismisses its menu on click-away."""
    if sys.platform != "win32":
        return 0
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    user32.GetAncestor.restype = ctypes.c_void_p
    user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    user32.SetForegroundWindow.restype = ctypes.c_int
    owner = int(user32.GetAncestor(root.winfo_id(), 2) or root.winfo_id())
    _ = user32.SetForegroundWindow(owner)
    return owner


def _finish_native_popup(owner: int) -> None:
    """Complete the native menu loop using the documented WM_NULL handshake."""
    if sys.platform != "win32" or not owner:
        return
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.PostMessageW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_size_t,
        ctypes.c_ssize_t,
    ]
    user32.PostMessageW.restype = ctypes.c_int
    _ = user32.PostMessageW(owner, 0, 0, 0)


def _cancel_native_popup(owner: int) -> None:
    """Cancel TrackPopupMenu from its Tk thread before unposting Tcl state."""
    if sys.platform != "win32" or not owner:
        return
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SendMessageW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_size_t,
        ctypes.c_ssize_t,
    ]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    _ = user32.SendMessageW(owner, 0x001F, 0, 0)  # WM_CANCELMODE
    # dismiss() is invoked by Tk's nested event loop, hence on the same thread
    # that entered TrackPopupMenu. EndMenu is the reliable loop terminator;
    # WM_CANCELMODE also covers owner-side menu state before Tcl unposts it.
    user32.EndMenu.argtypes = []
    user32.EndMenu.restype = ctypes.c_int
    _ = user32.EndMenu()
