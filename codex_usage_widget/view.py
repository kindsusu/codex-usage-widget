# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false
"""Pillow-rendered desktop card kept separate from refresh orchestration."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from PIL import ImageTk

from codex_usage_widget.desktop_render import (
    DesktopCardModel,
    DesktopHitRegions,
    HitRegion,
    HoverRegion,
    build_desktop_card_model,
    render_desktop_card,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from codex_usage_widget.presentation import SnapshotViewModel
    from codex_usage_widget.service import WidgetState
    from codex_usage_widget.theme import ThemeTokens


@dataclass(frozen=True, slots=True)
class ViewActions:
    """Commands emitted by the display without owning application state."""

    theme: Callable[[], None]
    opacity: Callable[[], None]
    mini: Callable[[], None]
    hide: Callable[[], None]
    refresh: Callable[[], None]
    menu: Callable[[int, int], None]
    visibility: Callable[[int, int], None]


@final
class WidgetView:
    """Frameless full and mini cards sharing one root and one data snapshot."""

    def __init__(
        self,
        root: tk.Tk,
        actions: ViewActions,
        pet_name: str,
        tokens: ThemeTokens,
    ) -> None:
        """Create an empty root-owned card; pet preference remains config-owned."""
        _ = pet_name
        self._root = root
        self._actions = actions
        self._light_theme = tokens.surface_primary == "#f4f3ee"
        self._canvas: tk.Canvas | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._model: DesktopCardModel | None = None
        self._mini = False
        self._factor = 1.0
        self._physical_scale = 1.0
        self._hover: HoverRegion | None = None
        self._pressed_region: HoverRegion | None = None
        self._regions: DesktopHitRegions | None = None
        self._pixel_size = (0, 0)
        self._menu_bind_id = root.bind("<Button-3>", self._open_menu, add="+")

    @property
    def pixel_size(self) -> tuple[int, int]:
        """Return the most recently rendered physical image size."""
        return self._pixel_size

    @property
    def brand_screen_region(self) -> HitRegion | None:
        """Return the full-card brand trigger in virtual-screen coordinates."""
        if self._canvas is None or self._regions is None or self._regions.brand is None:
            return None
        region = self._regions.brand
        x = self._canvas.winfo_rootx()
        y = self._canvas.winfo_rooty()
        return HitRegion(
            x + region.left,
            y + region.top,
            x + region.right,
            y + region.bottom,
        )

    def render(
        self,
        view_model: SnapshotViewModel | None,
        state: WidgetState,
        *,
        mini: bool,
        factor: float = 1.0,
        physical_scale: float = 1.0,
    ) -> None:
        """Render at logical size multiplied once by user and monitor scales."""
        self._model = build_desktop_card_model(view_model, state)
        self._mini = mini
        self._factor = factor
        self._physical_scale = physical_scale
        self._hover = None
        self._pressed_region = None
        self._dispose_surface()
        canvas = tk.Canvas(
            self._root,
            bg="#fdfdfb",
            borderwidth=0,
            highlightthickness=0,
            cursor="hand2" if mini else "arrow",
            takefocus=True,
        )
        self._canvas = canvas
        _ = canvas.pack(fill="both", expand=True)
        _ = canvas.bind("<Motion>", self._motion)
        _ = canvas.bind("<Leave>", self._leave)
        _ = canvas.bind("<ButtonPress-1>", self._press)
        _ = canvas.bind("<ButtonRelease-1>", self._release)
        _ = canvas.bind("<Double-Button-1>", self._double_click)
        self._paint()

    def dispose(self) -> None:
        """Release bindings and the root-owned image surface."""
        self._dispose_surface()
        if self._menu_bind_id is not None:
            self._root.unbind("<Button-3>", self._menu_bind_id)
            self._menu_bind_id = None

    def _paint(self) -> None:
        if self._canvas is None or self._model is None:
            return
        rendered = render_desktop_card(
            self._model,
            mode="mini" if self._mini else "full",
            light_theme=self._light_theme,
            scale=self._factor * self._physical_scale,
            hover_region=self._hover,
        )
        photo = ImageTk.PhotoImage(rendered.image, master=self._canvas)
        self._photo = photo
        self._regions = rendered.hit_regions
        self._pixel_size = rendered.image.size
        _ = self._canvas.configure(
            width=rendered.image.width, height=rendered.image.height
        )
        _ = self._canvas.delete("all")
        _ = self._canvas.create_image(0, 0, image=photo, anchor="nw")
        _ = self._root.geometry(f"{rendered.image.width}x{rendered.image.height}")

    def _motion(self, event: tk.Event[tk.Misc]) -> None:
        hover = self._region_at(event.x, event.y)
        if hover != self._hover:
            self._hover = hover
            self._paint()

    def _leave(self, _event: tk.Event[tk.Misc]) -> None:
        if self._hover is not None:
            self._hover = None
            self._paint()

    def _press(self, event: tk.Event[tk.Misc]) -> str | None:
        self._pressed_region = self._region_at(event.x, event.y)
        if self._pressed_region is not None:
            _ = self._canvas.focus_set() if self._canvas is not None else None
            return "break"
        return None

    def _release(self, event: tk.Event[tk.Misc]) -> str | None:
        region = self._region_at(event.x, event.y)
        pressed_region, self._pressed_region = self._pressed_region, None
        if pressed_region is None:
            return None
        if region != pressed_region:
            return "break"
        if pressed_region == "brand":
            self._actions.visibility(event.x_root, event.y_root)
            return "break"
        if pressed_region == "mode":
            self._actions.mini()
            return "break"
        return "break"

    def _double_click(self, event: tk.Event[tk.Misc]) -> str | None:
        if self._mini and self._region_at(event.x, event.y) is None:
            self._actions.mini()
            return "break"
        return None

    def _region_at(self, x: int, y: int) -> HoverRegion | None:
        if self._regions is None:
            return None
        if self._regions.brand is not None and self._regions.brand.contains(x, y):
            return "brand"
        return "mode" if self._regions.mode.contains(x, y) else None

    def _dispose_surface(self) -> None:
        if self._canvas is not None:
            self._canvas.destroy()
            self._canvas = None
        self._photo = None
        self._regions = None
        self._pressed_region = None

    def _open_menu(self, event: tk.Event[tk.Misc]) -> None:
        self._actions.menu(event.x_root, event.y_root)
