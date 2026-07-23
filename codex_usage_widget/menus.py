# pyright: reportAny=false, reportUnknownArgumentType=false, reportUnknownMemberType=false
"""Native popup menus and opacity controls for the compact widget."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import TYPE_CHECKING

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
    tokens = theme_tokens(config.theme)
    menu = _new_menu(root, tokens)
    # Rebuilt on every popup, so each variable snapshots the CURRENT config.
    # These BooleanVars MUST stay referenced: an unreferenced tk.BooleanVar is
    # garbage-collected immediately, which unsets its Tcl variable and makes the
    # checkbutton render unchecked. Named locals stay alive across the modal
    # tk_popup below, so the checkbuttons reflect live state while displayed.
    theme_on = tk.BooleanVar(menu, value=config.theme is ThemeName.DARK)
    mini_on = tk.BooleanVar(menu, value=config.mini_mode)
    topmost_on = tk.BooleanVar(menu, value=config.smart_topmost)
    _ = menu.add_command(label="새로고침", command=callbacks.refresh)
    _ = menu.add_checkbutton(
        label="다크/라이트 전환",
        command=callbacks.theme,
        variable=theme_on,
    )
    _ = menu.add_checkbutton(
        label="미니모드",
        command=callbacks.mini,
        variable=mini_on,
    )
    _ = menu.add_checkbutton(
        label="스마트 위",
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
    _ = menu.add_command(label="트레이로 숨기기", command=callbacks.hide)
    _ = menu.add_command(label="종료", command=callbacks.exit_app)
    # tk_popup is modal on Windows: it blocks until the menu is dismissed by any
    # route (selection, ESC, or click-away), so the finally is the one reliable
    # place to resume topmost -- <Unmap> does not fire dependably on every close.
    callbacks.menu_opened()
    try:
        menu.tk_popup(x, y)
    finally:
        callbacks.menu_closed()


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
