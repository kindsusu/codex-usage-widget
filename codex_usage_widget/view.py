# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false
"""Token-driven native view kept separate from refresh orchestration."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from codex_usage_widget.mini_view import MiniSurface, MiniSurfaceSpec
from codex_usage_widget.view_text import empty_text, footer_text
from codex_usage_widget.widgets import PetCanvas, UsageMeter, VectorIconButton

if TYPE_CHECKING:
    from collections.abc import Callable

    from codex_usage_widget.icons import IconName
    from codex_usage_widget.presentation import SnapshotViewModel, UsageRowViewModel
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


@final
class WidgetView:
    """Frameless full and mini layouts sharing one root window."""

    def __init__(
        self,
        root: tk.Tk,
        actions: ViewActions,
        pet_name: str,
        tokens: ThemeTokens,
    ) -> None:
        """Create an initially empty root-owned surface."""
        self._root = root
        self._actions = actions
        self._pet_name = pet_name
        self._tokens = tokens
        self._body = tk.Frame(root)
        self._surface: tk.Frame | None = None
        self._mini_surface: MiniSurface | None = None
        self._pets: list[PetCanvas] = []
        self._menu_bind_id = root.bind("<Button-3>", self._open_menu, add="+")

    def render(
        self,
        view_model: SnapshotViewModel | None,
        state: WidgetState,
        *,
        mini: bool,
    ) -> None:
        """Rebuild the compact surface from immutable state."""
        self._dispose_surface()
        if mini:
            self._mini_surface = MiniSurface(
                self._root,
                MiniSurfaceSpec(
                    view_model,
                    state,
                    self._tokens,
                    self._actions.mini,
                ),
            )
        else:
            self._render_full(view_model, state)

    def dispose(self) -> None:
        """Release bindings, surfaces, and all scheduled pet callbacks."""
        self._dispose_surface()
        if self._menu_bind_id is not None:
            self._root.unbind("<Button-3>", self._menu_bind_id)
            self._menu_bind_id = None

    def _render_full(
        self, view_model: SnapshotViewModel | None, state: WidgetState
    ) -> None:
        tokens = self._tokens
        outer = tk.Frame(
            self._root,
            bg=tokens.surface_primary,
            highlightbackground=tokens.bar_background,
            highlightthickness=1,
            padx=tokens.space_5,
            pady=tokens.space_5,
        )
        self._surface = outer
        _ = outer.pack(fill="both", expand=True)
        header = tk.Frame(outer, bg=tokens.surface_primary)
        _ = header.pack(fill="x", pady=(0, tokens.space_3))
        pet = PetCanvas(header, self._pet_name, tokens)
        self._pets.append(pet)
        _ = pet.pack(side="left")
        title = tk.Label(
            header,
            text="Codex" if view_model is None else view_model.title,
            bg=tokens.surface_primary,
            fg=tokens.text_primary,
            font=(tokens.font_family, 10, "bold"),
        )
        _ = title.pack(side="left", padx=(tokens.space_2, 0))
        controls = tk.Frame(header, bg=tokens.surface_primary)
        _ = controls.pack(side="right")
        specs: tuple[tuple[IconName, Callable[[], None], str], ...] = (
            ("theme", self._actions.theme, "라이트/다크 테마 (Ctrl+T)"),
            ("opacity", self._actions.opacity, "투명도 조절"),
            ("mini", self._actions.mini, "미니 모드 (Ctrl+M)"),
            ("close", self._actions.hide, "트레이로 숨기기 (Esc)"),
        )
        for icon, callback, tooltip in specs:
            button = VectorIconButton(controls, icon, callback, tooltip, tokens)
            _ = button.pack(side="left", padx=(tokens.space_1, 0))
        divider = tk.Frame(outer, height=1, bg=tokens.bar_background)
        _ = divider.pack(fill="x", pady=(0, tokens.space_3))
        self._body = tk.Frame(outer, bg=tokens.surface_primary)
        _ = self._body.pack(fill="x")
        if view_model is None:
            self._render_empty(state)
        else:
            for row in view_model.rows:
                self._render_row(row)
        footer = tk.Label(
            outer,
            text=footer_text(view_model, state),
            bg=tokens.surface_primary,
            fg=tokens.status_error if state.failure is not None else tokens.text_muted,
            anchor="w",
            font=(tokens.font_family, 7),
        )
        _ = footer.pack(fill="x", pady=(tokens.space_3, 0))
        self._root.geometry(f"{tokens.full_width}x{max(104, outer.winfo_reqheight())}")

    def _render_row(self, row: UsageRowViewModel) -> None:
        tokens = self._tokens
        card = tk.Frame(self._body, bg=tokens.surface_primary)
        _ = card.pack(fill="x", pady=(0, tokens.row_gap))
        line = tk.Frame(card, bg=tokens.surface_primary)
        _ = line.pack(fill="x")
        _ = tk.Label(
            line,
            text=row.label,
            bg=tokens.surface_primary,
            fg=tokens.text_primary,
            font=(tokens.font_family, 9, "bold"),
        ).pack(side="left")
        _ = tk.Label(
            line,
            text=row.percent_text,
            bg=tokens.surface_primary,
            fg=tokens.text_primary,
            font=(tokens.font_family, 9, "bold"),
        ).pack(side="right")
        meter = UsageMeter(card, tokens)
        _ = meter.pack(fill="x", pady=(tokens.space_2, tokens.space_1))
        meter.render(row.window.used_percent, row.meter_color)
        _ = tk.Label(
            card,
            text=row.reset_text,
            bg=tokens.surface_primary,
            fg=tokens.text_secondary,
            anchor="w",
            font=(tokens.font_family, 8),
        ).pack(fill="x")

    def _render_empty(self, state: WidgetState) -> None:
        tokens = self._tokens
        container = tk.Frame(
            self._body,
            bg=tokens.surface_secondary,
            padx=tokens.space_3,
            pady=tokens.space_5,
        )
        _ = container.pack(fill="x", pady=(tokens.space_1, tokens.space_2))
        if state.failure is not None:
            marker = tk.Canvas(
                container,
                width=16,
                height=16,
                bg=tokens.surface_secondary,
                highlightthickness=0,
            )
            _ = marker.pack(side="left", padx=(0, tokens.space_3))
            _ = marker.create_oval(2, 2, 14, 14, outline=tokens.status_error, width=1.5)
            _ = marker.create_line(8, 5, 8, 9, fill=tokens.status_error, width=1.5)
            _ = marker.create_oval(7, 11, 9, 13, fill=tokens.status_error, outline="")
        _ = tk.Label(
            container,
            text=empty_text(state),
            bg=tokens.surface_secondary,
            fg=tokens.text_primary if state.failure is None else tokens.status_error,
            anchor="w",
            justify="left",
            wraplength=tokens.bar_width,
            font=(tokens.font_family, 9),
        ).pack(side="left", fill="x", expand=True)

    def _dispose_surface(self) -> None:
        if self._mini_surface is not None:
            self._mini_surface.dispose()
            self._mini_surface = None
        for pet in self._pets:
            pet.dispose()
        self._pets.clear()
        if self._surface is not None:
            self._surface.destroy()
            self._surface = None

    def _open_menu(self, event: tk.Event[tk.Misc]) -> None:
        self._actions.menu(event.x_root, event.y_root)
