# pyright: reportUnknownMemberType=false
"""Window background and transparency attributes."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk

    from codex_usage_widget.theme import ThemeTokens


def apply_window_surface(root: tk.Tk, tokens: ThemeTokens, *, mini: bool) -> None:
    """Apply the chroma key used outside both rounded desktop card modes."""
    _ = mini
    background = tokens.mini_background_key
    _ = root.configure(bg=background)
    _ = root.attributes("-transparentcolor", tokens.mini_background_key)
