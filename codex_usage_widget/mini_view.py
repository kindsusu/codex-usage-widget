# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false
"""Mini-mode surface with root-level restore interaction."""

from __future__ import annotations

import io
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol, TypeAlias, final

from PIL import Image, ImageTk

from codex_usage_widget.assets import load_mini_icon_png
from codex_usage_widget.presentation import percent_text
from codex_usage_widget.view_text import short_label

if TYPE_CHECKING:
    from codex_usage_widget.presentation import SnapshotViewModel, UsageRowViewModel
    from codex_usage_widget.service import WidgetState
    from codex_usage_widget.theme import ThemeTokens

BindingCallback: TypeAlias = Callable[[], str]
_BATTERY_TEXT_SWITCH_PERCENT: Final = 50.0
_OPAQUE_ALPHA_THRESHOLD: Final = 128


class BindingTarget(Protocol):
    """Minimal tree and binding seam used by mini-mode interactions."""

    def children(self) -> tuple[BindingTarget, ...]:
        """Return direct descendants."""
        ...

    def bind(self, sequence: str, callback: BindingCallback) -> str:
        """Register and identify one binding."""
        ...

    def unbind(self, sequence: str, binding_id: str) -> None:
        """Remove one identified binding."""
        ...


@final
class TkBindingTarget:
    """Adapt one Tk widget tree to the testable binding seam."""

    def __init__(self, widget: tk.Misc) -> None:
        """Wrap a concrete Tk widget."""
        self._widget = widget

    def children(self) -> tuple[BindingTarget, ...]:
        """Return wrapped direct descendants."""
        return tuple(TkBindingTarget(child) for child in self._widget.winfo_children())

    def bind(self, sequence: str, callback: BindingCallback) -> str:
        """Add a callback that can stop root drag propagation."""

        def handle(_event: tk.Event[tk.Misc]) -> str:
            return callback()

        return self._widget.bind(sequence, handle, add="+")

    def unbind(self, sequence: str, binding_id: str) -> None:
        """Remove one callback without disturbing unrelated bindings."""
        self._widget.unbind(sequence, binding_id)


@final
class RestoreBindingGroup:
    """Bind restore and release guards across one complete widget tree."""

    def __init__(self, root: BindingTarget, restore: Callable[[], None]) -> None:
        """Bind every current descendant and guard restore to one call."""
        self._restore = restore
        self._restored = False
        self._bindings: list[tuple[BindingTarget, str, str]] = []
        for target in _binding_targets(root):
            restore_id = target.bind("<Double-Button-1>", self._restore_once)
            release_id = target.bind("<ButtonRelease-1>", _stop_root_release)
            self._bindings.extend(
                (
                    (target, "<Double-Button-1>", restore_id),
                    (target, "<ButtonRelease-1>", release_id),
                )
            )

    def dispose(self) -> None:
        """Remove all exact function ids in reverse registration order."""
        for target, sequence, binding_id in reversed(self._bindings):
            target.unbind(sequence, binding_id)
        self._bindings.clear()

    def _restore_once(self) -> str:
        if not self._restored:
            self._restored = True
            self._restore()
        return "break"


def _binding_targets(root: BindingTarget) -> tuple[BindingTarget, ...]:
    descendants = tuple(
        nested for child in root.children() for nested in _binding_targets(child)
    )
    return (root, *descendants)


def _stop_root_release() -> str:
    return "break"


def mini_battery_fill_width(used_percent: float, inner_width: int) -> float:
    """Clamp a mini usage value to the battery's inner width."""
    return max(0.0, min(float(inner_width), used_percent / 100 * inner_width))


def mini_remaining_percent(used_percent: float) -> float:
    """Convert a used percentage into a clamped remaining percentage."""
    return 100.0 - max(0.0, min(100.0, used_percent))


def mini_battery_text_color(used_percent: float, tokens: ThemeTokens) -> str:
    """Keep centered percentage text legible across filled and empty halves."""
    return (
        tokens.meter_text_on_fill
        if used_percent >= _BATTERY_TEXT_SWITCH_PERCENT
        else tokens.text_primary
    )


@final
@dataclass(frozen=True, slots=True)
class MiniSurfaceSpec:
    """Immutable inputs required to render a mini surface."""

    view_model: SnapshotViewModel | None
    state: WidgetState
    tokens: ThemeTokens
    restore: Callable[[], None]


@final
class MiniSurface:
    """Own mini widgets and restore bindings."""

    def __init__(
        self,
        root: tk.Tk,
        spec: MiniSurfaceSpec,
    ) -> None:
        """Build and bind one mini-mode surface."""
        self._root = root
        tokens = spec.tokens
        frame = tk.Frame(
            root,
            bg=tokens.mini_background_key,
            highlightthickness=0,
            padx=0,
            pady=0,
        )
        self._frame = frame
        _ = frame.pack(fill="both", expand=True)
        icon = Image.open(
            io.BytesIO(load_mini_icon_png(tokens.mini_icon_asset))
        ).convert(
            "RGBA",
        )
        icon_size = (tokens.mini_icon_size, tokens.mini_icon_size)
        alpha = icon.getchannel("A").resize(icon_size, Image.Resampling.NEAREST)
        alpha = alpha.point(_binary_alpha)
        icon = icon.convert("RGB").resize(icon_size, Image.Resampling.LANCZOS)
        icon.putalpha(alpha)
        self._icon_photo = ImageTk.PhotoImage(icon)
        icon_canvas = tk.Canvas(
            frame,
            width=tokens.mini_icon_size,
            height=tokens.mini_icon_size,
            bg=tokens.mini_background_key,
            borderwidth=0,
            highlightthickness=0,
        )
        _ = icon_canvas.pack(side="left", padx=(0, tokens.mini_gap))
        _ = icon_canvas.create_image(
            tokens.mini_icon_size / 2,
            tokens.mini_icon_size / 2,
            image=self._icon_photo,
        )
        content = tk.Frame(frame, bg=tokens.mini_background_key)
        _ = content.pack(side="left")
        rows = () if spec.view_model is None else spec.view_model.mini_rows
        if not rows:
            _ = tk.Label(
                content,
                text="확인 중…" if spec.state.failure is None else "연결 필요",
                bg=tokens.mini_background_key,
                fg=tokens.text_secondary,
                font=(tokens.font_family, 8),
            ).pack(expand=True)
        for row in rows:
            _render_row(content, row, tokens)
        self._bindings = RestoreBindingGroup(TkBindingTarget(frame), spec.restore)
        root.geometry(f"{tokens.mini_width}x{tokens.mini_height}")

    def dispose(self) -> None:
        """Release bindings and destroy mini widgets."""
        self._bindings.dispose()
        self._frame.destroy()


def _render_row(
    parent: tk.Misc,
    row: UsageRowViewModel,
    tokens: ThemeTokens,
) -> None:
    line = tk.Frame(parent, bg=tokens.mini_background_key)
    _ = line.pack(fill="x")
    label = tk.Canvas(
        line,
        width=tokens.mini_label_width,
        height=tokens.mini_battery_height,
        bg=tokens.mini_background_key,
        highlightthickness=0,
    )
    _ = label.pack(side="left", padx=(0, tokens.mini_gap))
    label_text = short_label(row.label)
    if label_text == "W":
        _ = label.create_line(1, 2, 3, 12, fill=tokens.text_primary, width=2)
        _ = label.create_line(3, 12, 7, 6, fill=tokens.text_primary, width=2)
        _ = label.create_line(7, 6, 11, 12, fill=tokens.text_primary, width=2)
        _ = label.create_line(11, 12, 13, 2, fill=tokens.text_primary, width=2)
    else:
        _ = label.create_text(
            0,
            tokens.mini_battery_height / 2,
            anchor="w",
            text=label_text,
            fill=tokens.text_primary,
            font=(tokens.font_family, 8, "bold"),
        )
    battery = tk.Canvas(
        line,
        width=tokens.mini_battery_width,
        height=tokens.mini_battery_height,
        bg=tokens.mini_background_key,
        highlightthickness=0,
    )
    _ = battery.pack(side="right")
    body_right = tokens.mini_battery_width - 5
    body_bottom = tokens.mini_battery_height - 1
    _ = battery.create_rectangle(
        1,
        1,
        body_right,
        body_bottom,
        fill=tokens.bar_background,
        outline=tokens.control_default,
        width=1,
    )
    _ = battery.create_rectangle(
        body_right + 1,
        4,
        tokens.mini_battery_width - 1,
        tokens.mini_battery_height - 4,
        fill=tokens.control_default,
        outline=tokens.control_default,
    )
    inner_width = body_right - 4
    remaining = mini_remaining_percent(row.window.used_percent)
    fill_width = mini_battery_fill_width(remaining, inner_width)
    if fill_width > 0:
        _ = battery.create_rectangle(
            3,
            3,
            3 + fill_width,
            body_bottom - 2,
            fill=row.meter_color,
            outline="",
        )
    _ = battery.create_text(
        body_right / 2,
        tokens.mini_battery_height / 2,
        text=percent_text(remaining),
        fill=mini_battery_text_color(remaining, tokens),
        font=(tokens.font_family, 7, "bold"),
    )


def _binary_alpha(value: float) -> int:
    return 255 if value >= _OPAQUE_ALPHA_THRESHOLD else 0
