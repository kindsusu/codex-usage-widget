# pyright: reportUnknownMemberType=false
"""Window background and transparency attributes."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk

    from codex_usage_widget.theme import ThemeTokens


def apply_window_surface(root: tk.Tk, tokens: ThemeTokens, *, mini: bool) -> None:
    """Apply an opaque full surface or chroma-keyed mini surface."""
    background = tokens.mini_background_key if mini else tokens.surface_primary
    _ = root.configure(bg=background)
    _ = root.attributes(
        "-transparentcolor",
        tokens.mini_background_key if mini else "",
    )
