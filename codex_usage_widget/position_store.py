"""Render-free persistence for native window positions."""

from dataclasses import replace
from pathlib import Path

from codex_usage_widget.config import WidgetConfig, save_config
from codex_usage_widget.windows import WindowPosition


def persist_window_position(
    config_path: Path,
    config: WidgetConfig,
    position: WindowPosition,
) -> WidgetConfig:
    """Persist a new window position without rebuilding the rendered surface."""
    updated = replace(config, position=position)
    save_config(config_path, updated)
    return updated
