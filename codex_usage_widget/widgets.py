# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false
"""Token-driven Tk canvas primitives for the native widget."""

from __future__ import annotations

import io
import tkinter as tk
from typing import TYPE_CHECKING, Literal, TypeAlias, final

from PIL import Image, ImageTk

from codex_usage_widget.assets import load_pet_png
from codex_usage_widget.icons import IconAppearance, IconName, draw_icon
from codex_usage_widget.pet_image import prepare_pet_image

if TYPE_CHECKING:
    from collections.abc import Callable

    from codex_usage_widget.theme import ThemeTokens

ControlState: TypeAlias = Literal["idle", "hover", "pressed"]


def action_control_background(tokens: ThemeTokens, state: ControlState) -> str:
    """Resolve the action control surface for its interaction state."""
    if state == "hover":
        return tokens.control_surface_hover
    if state == "pressed":
        return tokens.control_surface_pressed
    return tokens.surface_primary


@final
class Tooltip:
    """A compact token-colored tooltip."""

    def __init__(self, owner: tk.Misc, text: str, tokens: ThemeTokens) -> None:
        """Attach a tooltip to one compact action control."""
        self._owner = owner
        self._text = text
        self._tokens = tokens
        self._popup: tk.Toplevel | None = None
        self._timer_id: str | None = None
        _ = owner.bind("<Enter>", self._schedule, add="+")
        _ = owner.bind("<Leave>", self._hide, add="+")

    def _schedule(self, _event: tk.Event[tk.Misc]) -> None:
        if self._timer_id is None and self._popup is None:
            self._timer_id = self._owner.after(500, self._show)

    def _show(self) -> None:
        self._timer_id = None
        if self._popup is not None:
            return
        popup = tk.Toplevel(self._owner)
        _ = popup.overrideredirect(True)
        _ = popup.attributes("-topmost", True)
        x = self._owner.winfo_rootx()
        y = self._owner.winfo_rooty() + self._owner.winfo_height() + 5
        _ = popup.geometry(f"+{x}+{y}")
        _ = tk.Label(
            popup,
            text=self._text,
            bg=self._tokens.tooltip_surface,
            fg=self._tokens.tooltip_text,
            padx=self._tokens.space_3,
            pady=self._tokens.space_1,
            font=(self._tokens.font_family, 8),
        ).pack()
        self._popup = popup

    def _hide(self, _event: tk.Event[tk.Misc]) -> None:
        if self._timer_id is not None:
            self._owner.after_cancel(self._timer_id)
            self._timer_id = None
        if self._popup is not None:
            self._popup.destroy()
            self._popup = None


@final
class VectorIconButton(tk.Canvas):
    """A transparent, keyboard-accessible vector action control."""

    def __init__(
        self,
        parent: tk.Misc,
        icon: IconName,
        command: Callable[[], None],
        tooltip: str,
        tokens: ThemeTokens,
    ) -> None:
        """Create one focusable action control with a vector icon."""
        super().__init__(
            parent,
            width=tokens.control_size,
            height=tokens.control_size,
            bg=tokens.surface_primary,
            highlightthickness=0,
            cursor="hand2",
            takefocus=True,
        )
        self._icon: IconName = icon
        self._command = command
        self._tokens = tokens
        self._state: ControlState = "idle"
        self._focused = False
        self._icon_photo: ImageTk.PhotoImage | None = None
        _ = self.bind("<ButtonPress-1>", self._press)
        _ = self.bind("<ButtonRelease-1>", self._release)
        _ = self.bind("<Return>", self._keyboard)
        _ = self.bind("<space>", self._keyboard)
        _ = self.bind("<Enter>", self._enter)
        _ = self.bind("<Leave>", self._leave)
        _ = self.bind("<FocusIn>", self._focus_in)
        _ = self.bind("<FocusOut>", self._focus_out)
        self._tooltip = Tooltip(self, tooltip, tokens)
        self._draw()

    def _press(self, _event: tk.Event[tk.Misc]) -> str:
        _ = self.focus_set()
        self._state = "pressed"
        self._draw()
        return "break"

    def _release(self, _event: tk.Event[tk.Misc]) -> str:
        self._state = "hover"
        self._draw()
        self._command()
        return "break"

    def _keyboard(self, _event: tk.Event[tk.Misc]) -> str:
        self._command()
        return "break"

    def _enter(self, _event: tk.Event[tk.Misc]) -> None:
        if self._state != "pressed":
            self._state = "hover"
            self._draw()

    def _leave(self, _event: tk.Event[tk.Misc]) -> None:
        self._state = "idle"
        self._draw()

    def _focus_in(self, _event: tk.Event[tk.Misc]) -> None:
        self._focused = True
        self._draw()

    def _focus_out(self, _event: tk.Event[tk.Misc]) -> None:
        self._focused = False
        self._draw()

    def _draw(self) -> None:
        _ = self.delete("all")
        size = self._tokens.control_size
        _ = self.configure(bg=self._tokens.surface_primary)
        surface = action_control_background(self._tokens, self._state)
        if self._state != "idle":
            self._draw_surface(surface)
        if self._focused:
            _ = self.create_rectangle(
                1,
                1,
                size - 2,
                size - 2,
                outline=self._tokens.focus_ring,
                width=1,
            )
        color = (
            self._tokens.control_hover
            if self._state != "idle"
            else self._tokens.control_default
        )
        self._icon_photo = draw_icon(
            self,
            self._icon,
            IconAppearance(
                color,
                self._state != "idle",
                self._tokens.control_size,
                self._tokens.control_icon_size,
            ),
        )

    def _draw_surface(self, fill: str) -> None:
        size = self._tokens.control_size
        radius = 5
        _ = self.create_rectangle(
            radius,
            1,
            size - radius,
            size - 1,
            fill=fill,
            outline="",
        )
        _ = self.create_rectangle(
            1,
            radius,
            size - 1,
            size - radius,
            fill=fill,
            outline="",
        )
        for left, top in (
            (1, 1),
            (size - radius * 2 + 1, 1),
            (1, size - radius * 2 + 1),
            (size - radius * 2 + 1, size - radius * 2 + 1),
        ):
            _ = self.create_oval(
                left,
                top,
                left + radius * 2 - 1,
                top + radius * 2 - 1,
                fill=fill,
                outline="",
            )


@final
class UsageMeter(tk.Canvas):
    """A semantic usage meter accompanied by numeric text."""

    def __init__(self, parent: tk.Misc, tokens: ThemeTokens) -> None:
        """Create an empty meter using the configured dimensions."""
        super().__init__(
            parent,
            width=tokens.bar_width,
            height=tokens.bar_height,
            bg=tokens.surface_primary,
            highlightthickness=0,
        )
        self._tokens = tokens

    def render(self, used_percent: float, color: str) -> None:
        """Render a clamped percentage and semantic fill color."""
        _ = self.delete("all")
        width = self._tokens.bar_width
        height = self._tokens.bar_height
        _ = self.create_rectangle(
            0, 1, width, height - 1, fill=self._tokens.bar_background, outline=""
        )
        fill_width = max(0.0, min(float(width), used_percent / 100 * width))
        if fill_width > 0:
            _ = self.create_rectangle(
                0, 1, fill_width, height - 1, fill=color, outline=""
            )


@final
class PetCanvas(tk.Canvas):
    """A background-safe pixel pet with cancellable breathing motion."""

    def __init__(self, parent: tk.Misc, pet_name: str, tokens: ThemeTokens) -> None:
        """Load one pet and schedule its restrained motion."""
        size = tokens.pet_canvas_size
        super().__init__(
            parent,
            width=size,
            height=size,
            bg=tokens.surface_primary,
            highlightthickness=0,
        )
        source = Image.open(io.BytesIO(load_pet_png(pet_name))).convert("RGBA")
        prepared = prepare_pet_image(source, tokens.pet_size)
        self._photo = ImageTk.PhotoImage(prepared)
        center = size // 2
        self._image_id = self.create_image(center, center, image=self._photo)
        self._center = center
        self._phase = 0
        self._after_id: str | None = self.after(700, self._animate)
        self._disposed = False

    def dispose(self) -> None:
        """Cancel future animation work before the canvas is destroyed."""
        self._disposed = True
        if self._after_id is not None:
            self.after_cancel(self._after_id)
            self._after_id = None

    def _animate(self) -> None:
        if self._disposed:
            return
        self._phase = (self._phase + 1) % 4
        offset = (0, -1, 0, 1)[self._phase]
        _ = self.coords(self._image_id, self._center, self._center + offset)
        self._after_id = self.after(700, self._animate)
